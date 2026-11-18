"""
Generate FAKE Domain rental snapshots into raw.domain_rent_listings so the dbt models can be
built and demoed before you have a Domain API key.

Payload shape mirrors what ingest_domain.py stores (propertyDetails / priceDetails / dateListed),
including messy price strings ("$2,800 pcm", "$600 - $650", "Contact agent").

!! Use a separate database (or truncate afterwards). Never mix fake rows with real snapshots.

    python scripts/generate_fake_domain.py --start 2026-07-01 --end 2026-11-18 --truncate
"""
from __future__ import annotations

import argparse
import copy
import csv
import os
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# rough $/week asking rents by (type, bedrooms); scaled per suburb below
BASE = {("ApartmentUnitFlat", 1): 560, ("ApartmentUnitFlat", 2): 720, ("ApartmentUnitFlat", 3): 900,
        ("House", 3): 760, ("House", 4): 900, ("House", 5): 1100,
        ("Townhouse", 2): 640, ("Townhouse", 3): 780}
MIX = list(BASE)
WEIGHTS = [20, 30, 8, 12, 8, 2, 8, 12]


def price_text(rng: random.Random, weekly: int) -> str:
    r = rng.random()
    if r < 0.06:
        return "Contact agent"
    if r < 0.12:
        return f"${round(weekly * 52 / 12, -1):,.0f} pcm"
    if r < 0.18:
        return f"${weekly} - ${weekly + 30}"
    if r < 0.40:
        return f"${weekly} pw"
    return f"${weekly} per week"


def generate(start: date, end: date, seed: int = 42):
    rng = random.Random(seed)
    suburbs = list(csv.DictReader(open(ROOT / "config" / "suburbs.csv")))
    factor = {s["suburb"]: rng.uniform(0.85, 1.25) for s in suburbs}
    next_id = 2_000_000
    live: list[dict] = []
    rows = []
    d = start
    while d <= end:
        for s in suburbs:                                   # new listings today
            for _ in range(rng.choice([0, 1, 1, 2, 2, 3])):
                ptype, beds = rng.choices(MIX, WEIGHTS)[0]
                ask = int(round(BASE[(ptype, beds)] * factor[s["suburb"]] * rng.uniform(0.9, 1.15), -1))
                next_id += 1
                live.append({
                    "id": next_id, "suburb": s, "ask": ask, "listed": d,
                    "lease_on": d + timedelta(days=max(3, int(rng.expovariate(1 / 18)))),
                    "payload": {
                        "id": next_id,
                        "_synthetic": True,          # lets exports/dashboards flag demo data
                        "dateListed": f"{d.isoformat()}T09:00:00",
                        "propertyDetails": {
                            "suburb": s["suburb"].upper(), "postcode": s["postcode"], "state": "QLD",
                            "propertyType": ptype, "bedrooms": beds, "bathrooms": max(1, beds - 1),
                            "carspaces": rng.choice([0, 1, 1, 2]),
                            "latitude": -27.47 + rng.uniform(-0.1, 0.1), "longitude": 153.02 + rng.uniform(-0.1, 0.1),
                        },
                        "priceDetails": {"displayPrice": price_text(rng, ask)},
                    },
                })
        still = []
        for l in live:                                      # snapshot every live listing
            if d >= l["lease_on"]:
                continue
            if (d - l["listed"]).days in (14, 21) and rng.random() < 0.35:   # price cut
                l["ask"] = int(l["ask"] * 0.95)
                l["payload"]["priceDetails"]["displayPrice"] = f"${l['ask']} per week"
            rows.append((l["id"], d, l["suburb"]["suburb"], l["suburb"]["postcode"], copy.deepcopy(l["payload"])))
            still.append(l)
        live = still
        d += timedelta(days=1)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=date.fromisoformat, default=date(2026, 7, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date.today())
    ap.add_argument("--truncate", action="store_true", help="empty raw.domain_rent_listings first")
    args = ap.parse_args()

    import psycopg
    from psycopg.types.json import Jsonb

    rows = generate(args.start, args.end)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        if args.truncate:
            cur.execute("TRUNCATE raw.domain_rent_listings")
        cur.executemany(
            """INSERT INTO raw.domain_rent_listings
               (listing_id, snapshot_date, search_suburb, search_postcode, payload)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (listing_id, snapshot_date) DO UPDATE SET payload = EXCLUDED.payload""",
            [(i, d, s, p, Jsonb(pl)) for i, d, s, p, pl in rows],
        )
        conn.commit()
    print(f"inserted {len(rows):,} fake snapshot rows ({args.start} -> {args.end})")


if __name__ == "__main__":
    main()
