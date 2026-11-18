"""
Export the dbt marts to CSV for Power BI (powerbi/data/). Use this when Power BI cannot reach
your Postgres directly (e.g. no gateway for a cloud DB), or to share a reproducible snapshot.

Writes a manifest.json with row counts and whether the Domain data is synthetic
(rows created by scripts/generate_fake_domain.py carry "_synthetic": true).

    python scripts/export_marts.py                 # -> powerbi/data/*.csv
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "powerbi" / "data"
MARTS = [
    "mart_rent_gap_suburb_quarter",
    "mart_rta_suburb_latest",
    "mart_rta_suburb_trend",
    "mart_listing_velocity_suburb_month",
]


def select_sql(cur, table: str) -> str:
    """SELECT with booleans rendered as true/false (Postgres COPY writes t/f, which Power Query
    cannot type as logical)."""
    cols = cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'marts' AND table_name = %s ORDER BY ordinal_position", (table,)).fetchall()
    parts = [f"CASE WHEN {c} THEN 'true' WHEN NOT {c} THEN 'false' END AS {c}" if t == "boolean" else c
             for c, t in cols]
    return f"SELECT {', '.join(parts)} FROM marts.{table}"


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from envconfig import database_url, load_env
    load_env()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tables": {}}

    with psycopg.connect(database_url()) as conn, conn.cursor() as cur:
        for name in MARTS:
            path = OUT / f"{name}.csv"
            with path.open("wb") as f, cur.copy(
                    f"COPY ({select_sql(cur, name)}) TO STDOUT WITH (FORMAT csv, HEADER true)") as cp:
                for chunk in cp:
                    f.write(chunk)
            n = cur.execute(f"SELECT count(*) FROM marts.{name}").fetchone()[0]
            manifest["tables"][name] = n
            print(f"{name:40s} {n:>8,} rows -> {path.relative_to(ROOT)}")

        total, fake = cur.execute(
            "SELECT count(*), count(*) FILTER (WHERE (payload ->> '_synthetic')::boolean) "
            "FROM raw.domain_rent_listings").fetchone()
        rta_q = cur.execute("SELECT max(quarter_end) FROM raw.rta_bond_stats").fetchone()[0]

    manifest["domain_snapshot_rows"] = total
    manifest["domain_data_is_synthetic"] = bool(total) and fake == total
    manifest["domain_synthetic_share"] = round(fake / total, 3) if total else None
    manifest["rta_latest_quarter"] = rta_q.isoformat() if rta_q else None
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if fake:
        print(f"!! {fake:,}/{total:,} Domain rows are SYNTHETIC - label the dashboard as demo data")


if __name__ == "__main__":
    main()
