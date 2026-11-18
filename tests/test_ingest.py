"""Tests run without a Domain key: the HTTP session is faked."""
import json
import os
from datetime import date

import pytest

import ingest_domain as ing


def make_listing(i, suburb="Toowong", price="$650 per week"):
    return {
        "id": i,
        "priceDetails": {"displayPrice": price},
        "propertyDetails": {"suburb": suburb, "postcode": "4066", "propertyType": "ApartmentUnitFlat", "bedrooms": 2},
        "dateListed": "2026-11-10T09:00:00",
    }


class FakeResp:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    """Returns a token, then pages of search results; can inject a 429 first."""

    def __init__(self, pages, first_429=False):
        self.pages, self.first_429, self.search_bodies = pages, first_429, []

    def post(self, url, **kw):
        if url == ing.TOKEN_URL:
            return FakeResp(200, {"access_token": "t", "expires_in": 3600})
        if self.first_429:
            self.first_429 = False
            return FakeResp(429, headers={"Retry-After": "0"})
        self.search_bodies.append(kw["json"])
        return FakeResp(200, self.pages[kw["json"]["pageNumber"] - 1])


def test_pagination_and_retry():
    page1 = [{"type": "PropertyListing", "listing": make_listing(i)} for i in range(100)]
    page2 = [{"type": "PropertyListing", "listing": make_listing(i)} for i in range(100, 130)]
    sess = FakeSession([page1, page2], first_429=True)
    client = ing.DomainClient("id", "secret", session=sess)

    items = client.search_rentals("Toowong", "QLD", "4066")

    assert len(items) == 130
    assert [b["pageNumber"] for b in sess.search_bodies] == [1, 2]
    assert sess.search_bodies[0]["listingType"] == "Rent"
    assert client.calls == 3  # 429 + 2 pages


def test_flatten_projects_and_dedupe():
    items = [
        {"type": "PropertyListing", "listing": make_listing(1)},
        {"type": "Project", "listings": [make_listing(2), make_listing(3)]},
        {"type": "PropertyListing", "listing": make_listing(1)},  # duplicate across pages
    ]
    assert sorted(l["id"] for l in ing.flatten_results(items)) == [1, 2, 3]


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")
def test_load_and_quicklook_view(tmp_path, monkeypatch):
    import psycopg

    dsn = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        conn.execute(open(ing.ROOT / "sql" / "001_raw_schema.sql").read())
        conn.execute("TRUNCATE raw.domain_rent_listings")

    snap = date(2026, 11, 18)
    rows = [
        (make_listing(1, price="$650 per week"), "Toowong", "4066"),
        (make_listing(2, price="$2,600 pcm"), "Toowong", "4066"),
        (make_listing(3, price="Contact agent"), "Toowong", "4066"),
    ]
    assert ing.load_to_postgres(dsn, snap, rows) == 3
    assert ing.load_to_postgres(dsn, snap, rows) == 3  # idempotent re-run: upsert, no duplicates

    with psycopg.connect(dsn) as conn:
        got = dict(conn.execute(
            "SELECT listing_id, weekly_rent FROM raw.v_domain_rent_quicklook ORDER BY 1").fetchall())
        n = conn.execute("SELECT count(*) FROM raw.domain_rent_listings").fetchone()[0]

    assert n == 3
    assert got == {1: 650, 2: 600, 3: None}  # 2600*12/52 = 600


def test_reload_from_raw(tmp_path, monkeypatch):
    monkeypatch.setattr(ing, "RAW_DIR", tmp_path)
    snap = date(2026, 11, 18)
    p = ing.raw_path(snap, "Toowong", "4066")
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps([{"type": "PropertyListing", "listing": make_listing(7)}]))

    rows = ing.read_snapshot_from_raw(snap, [{"suburb": "Toowong", "state": "QLD", "postcode": "4066"}])
    assert [r[0]["id"] for r in rows] == [7]
