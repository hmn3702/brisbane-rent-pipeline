"""
Ingest rental listings from the Domain API.

Flow:  Domain API  ->  raw JSON files (data/raw/...)  ->  Postgres raw.domain_rent_listings

Each run is one daily *snapshot*: every live rental listing in the configured
suburbs is stored with the snapshot date. Comparing snapshots over time later
gives you days-on-market and price changes (done in dbt, not here).

Usage:
    python ingest_domain.py                      # fetch today's snapshot + load to Postgres
    python ingest_domain.py --skip-db            # fetch + save JSON only
    python ingest_domain.py --reload-from-raw 2026-11-18   # reload saved JSON, no API calls
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

TOKEN_URL = "https://auth.domain.com.au/v1/connect/token"
SEARCH_URL = "https://api.domain.com.au/v1/listings/residential/_search"
SCOPE = "api_listings_read"
PAGE_SIZE = 100          # max page size for the search endpoint
MAX_RESULTS = 1000       # Domain caps a single search; split by suburb to stay under it
BRISBANE_TZ = ZoneInfo("Australia/Brisbane")

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw" / "domain"
SUBURBS_FILE = ROOT / "config" / "suburbs.csv"

log = logging.getLogger("ingest_domain")


# --------------------------------------------------------------------------- #
# API client
# --------------------------------------------------------------------------- #
class DomainClient:
    """Minimal Domain API client: OAuth client-credentials + paginated search."""

    def __init__(self, client_id: str, client_secret: str, session: requests.Session | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()
        self._token: str | None = None
        self._expires_at = 0.0
        self.calls = 0  # count search calls so you can watch your daily quota

    def _get_token(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        resp = self.session.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials", "scope": SCOPE},
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._expires_at = time.time() + int(body.get("expires_in", 3600)) - 60
        return self._token

    def _post_search(self, body: dict, max_retries: int = 5) -> list[dict]:
        for attempt in range(max_retries):
            headers = {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}
            resp = self.session.post(SEARCH_URL, json=body, headers=headers, timeout=30)
            self.calls += 1

            if resp.status_code == 401:            # token expired/revoked -> refresh once more
                self._token = None
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                log.warning("HTTP %s, retrying in %ss", resp.status_code, wait)
                time.sleep(wait)
                continue
            if resp.status_code == 403:
                raise RuntimeError(
                    "403 Forbidden: quota exhausted or your API key lacks the "
                    f"'{SCOPE}' scope. Check your plan in the Domain developer portal."
                )
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Search failed after {max_retries} attempts: {body}")

    def search_rentals(self, suburb: str, state: str, postcode: str) -> list[dict]:
        """Return all live rental search results for one suburb (raw API items)."""
        items: list[dict] = []
        page = 1
        while True:
            body = {
                "listingType": "Rent",
                "locations": [{
                    "state": state,
                    "suburb": suburb,
                    "postCode": postcode,
                    "includeSurroundingSuburbs": False,
                }],
                "pageSize": PAGE_SIZE,
                "pageNumber": page,
            }
            batch = self._post_search(body)
            items.extend(batch)
            if len(batch) < PAGE_SIZE or page * PAGE_SIZE >= MAX_RESULTS:
                if page * PAGE_SIZE >= MAX_RESULTS:
                    log.warning("%s hit the %s-result cap; split it by property type", suburb, MAX_RESULTS)
                break
            page += 1
        return items


# --------------------------------------------------------------------------- #
# Transform helpers
# --------------------------------------------------------------------------- #
def flatten_results(items: list[dict]) -> list[dict]:
    """Search results mix single listings and 'Project' groups (new developments).
    Return a flat list of listing objects."""
    listings = []
    for item in items:
        if item.get("type") == "PropertyListing" and "listing" in item:
            listings.append(item["listing"])
        elif item.get("type") == "Project":
            listings.extend(item.get("listings", []))
    # de-duplicate by id (a listing can appear twice across pages)
    return list({l["id"]: l for l in listings if "id" in l}.values())


def load_suburbs(path: Path = SUBURBS_FILE) -> list[dict]:
    with path.open(newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("suburb")]


def raw_path(snapshot: date, suburb: str, postcode: str) -> Path:
    safe = suburb.lower().replace(" ", "_")
    return RAW_DIR / f"snapshot_date={snapshot.isoformat()}" / f"{safe}_{postcode}.json"


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
UPSERT_SQL = """
INSERT INTO raw.domain_rent_listings
    (listing_id, snapshot_date, search_suburb, search_postcode, payload, ingested_at)
VALUES (%s, %s, %s, %s, %s, now())
ON CONFLICT (listing_id, snapshot_date) DO UPDATE
    SET payload = EXCLUDED.payload,
        search_suburb = EXCLUDED.search_suburb,
        search_postcode = EXCLUDED.search_postcode,
        ingested_at = now();
"""


def load_to_postgres(dsn: str, snapshot: date, rows: list[tuple[dict, str, str]]) -> int:
    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.executemany(
            UPSERT_SQL,
            [(l["id"], snapshot, sub, pc, Jsonb(l)) for l, sub, pc in rows],
        )
        conn.commit()
    return len(rows)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def fetch_snapshot(client: DomainClient, snapshot: date, suburbs: list[dict]) -> list[tuple[dict, str, str]]:
    rows = []
    for s in suburbs:
        items = client.search_rentals(s["suburb"], s["state"], s["postcode"])
        out = raw_path(snapshot, s["suburb"], s["postcode"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(items, ensure_ascii=False))   # keep the untouched API response
        listings = flatten_results(items)
        rows.extend((l, s["suburb"], s["postcode"]) for l in listings)
        log.info("%-18s %4d listings", s["suburb"], len(listings))
    return rows


def read_snapshot_from_raw(snapshot: date, suburbs: list[dict]) -> list[tuple[dict, str, str]]:
    rows = []
    for s in suburbs:
        p = raw_path(snapshot, s["suburb"], s["postcode"])
        if not p.exists():
            log.warning("missing raw file %s", p)
            continue
        rows.extend((l, s["suburb"], s["postcode"]) for l in flatten_results(json.loads(p.read_text())))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot-date", type=date.fromisoformat,
                        default=datetime.now(BRISBANE_TZ).date())
    parser.add_argument("--skip-db", action="store_true", help="save raw JSON only")
    parser.add_argument("--reload-from-raw", type=date.fromisoformat, metavar="DATE",
                        help="load an earlier snapshot from data/raw without calling the API")
    args = parser.parse_args(argv)

    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    suburbs = load_suburbs()

    if args.reload_from_raw:
        snapshot = args.reload_from_raw
        rows = read_snapshot_from_raw(snapshot, suburbs)
    else:
        snapshot = args.snapshot_date
        client = DomainClient(os.environ["DOMAIN_CLIENT_ID"], os.environ["DOMAIN_CLIENT_SECRET"])
        rows = fetch_snapshot(client, snapshot, suburbs)
        log.info("API search calls used this run: %d", client.calls)

    log.info("snapshot %s: %d listings across %d suburbs", snapshot, len(rows), len(suburbs))

    if not args.skip_db:
        n = load_to_postgres(os.environ["DATABASE_URL"], snapshot, rows)
        log.info("upserted %d rows into raw.domain_rent_listings", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
