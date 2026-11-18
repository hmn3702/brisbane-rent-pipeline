"""
Ingest Queensland RTA bond statistics (median rents, new bonds, bonds held).

Source: https://www.rta.qld.gov.au/forms-resources/rta-quarterly-data/median-rents-quarterly-data
Licence: CC BY 4.0, (c) The State of Queensland (Residential Tenancies Authority).

The workbook has 12 data sheets: 4 geography levels x 3 measures, all in the same
"wide" layout (rows = area + dwelling, columns = quarters). This script turns all
of them into ONE long table:

    geo_level | area_name | area_label | area_postcode | dwelling | dwelling_type | bedrooms
    | quarter_end | measure | value

The workbook always contains the full history and RTA may revise past quarters,
so each load is a full refresh (truncate + COPY in one transaction).

Usage:
    python ingest_rta.py                               # parse data/raw/rta/rta-bond-statistics.xlsx -> Postgres
    python ingest_rta.py --download                    # download the latest workbook first
    python ingest_rta.py --skip-db --csv-out data/processed/rta_long.csv
    python ingest_rta.py --download --geo suburb,state --if-changed   # hosted / scheduled run
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import openpyxl

RTA_URL = "https://www.rta.qld.gov.au/sites/default/files/2023-04/rta-bond-statistics.xlsx"
ROOT = Path(__file__).resolve().parent
DEFAULT_XLSX = ROOT / "data" / "raw" / "rta" / "rta-bond-statistics.xlsx"

# Sheet number -> (geo_level, measure). Matched by the leading number because
# sheet names are inconsistent (e.g. '7 lga-rents ' has a trailing space).
SHEETS = {
    1: ("postcode", "median_rent"), 2: ("postcode", "new_bonds"), 3: ("postcode", "bonds_held"),
    4: ("suburb", "median_rent"),   5: ("suburb", "new_bonds"),   6: ("suburb", "bonds_held"),
    7: ("lga", "median_rent"),      8: ("lga", "new_bonds"),      9: ("lga", "bonds_held"),
    10: ("state", "median_rent"),   11: ("state", "new_bonds"),   12: ("state", "bonds_held"),
}

# Layout (1-based rows): row 6 = month labels, row 7 = years, data from row 9.
# Columns: C = area, D = dwelling, E.. = quarters.
MONTH_ROW, YEAR_ROW, FIRST_DATA_ROW = 6, 7, 9
AREA_COL, DWELLING_COL, FIRST_VALUE_COL = 2, 3, 4   # 0-based indexes into a row tuple

QUARTER_END = {"Mar": (3, 31), "Jun": (6, 30), "Sep": (9, 30), "Dec": (12, 31)}
DWELLING_RE = re.compile(r"^(Flat|House|Townhouse)\s+(\d)$")
AREA_PC_RE = re.compile(r"^(.*?)\s*\((\d{4})\)$")   # 'West End (4101)' -> ('West End', '4101')

COLUMNS = ["geo_level", "area_name", "area_label", "area_postcode", "dwelling",
           "dwelling_type", "bedrooms", "quarter_end", "measure", "value"]

log = logging.getLogger("ingest_rta")


@dataclass(frozen=True)
class Record:
    geo_level: str
    area_name: str          # exactly as in the workbook (unique key, e.g. 'West End (4101)')
    area_label: str         # cleaned display name ('West End')
    area_postcode: str | None
    dwelling: str           # as in workbook: 'Flat 2', 'All dwellings', 'Other'
    dwelling_type: str      # 'Flat' | 'House' | 'Townhouse' | 'All' | 'Other'
    bedrooms: int | None
    quarter_end: date
    measure: str
    value: float

    def as_row(self) -> list:
        return [getattr(self, c) for c in COLUMNS]


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def parse_dwelling(raw: str) -> tuple[str, int | None]:
    m = DWELLING_RE.match(raw.strip())
    if m:
        return m.group(1), int(m.group(2))
    if raw.strip().lower() == "all dwellings":
        return "All", None
    return raw.strip(), None


def parse_area(raw, geo_level: str) -> tuple[str, str, str | None]:
    """Return (area_name, area_label, area_postcode)."""
    if geo_level == "postcode":
        pc = str(int(raw)).zfill(4)
        return pc, pc, pc
    name = str(raw).strip()
    m = AREA_PC_RE.match(name)
    if m:                                   # duplicate suburb names carry their postcode
        return name, m.group(1), m.group(2)
    return name, name, None


def quarter_columns(month_row: tuple, year_row: tuple) -> dict[int, date]:
    cols = {}
    for i in range(FIRST_VALUE_COL, len(month_row)):
        mon, yr = month_row[i], year_row[i]
        if mon is None and yr is None:
            continue
        if mon not in QUARTER_END or not isinstance(yr, int):
            raise ValueError(f"Unexpected quarter header at column {i + 1}: {mon!r} {yr!r}")
        m, d = QUARTER_END[mon]
        cols[i] = date(yr, m, d)
    if not cols:
        raise ValueError("No quarter columns found - has the workbook layout changed?")
    return cols


def find_sheet(wb, number: int):
    for ws in wb.worksheets:
        if re.match(rf"^\s*{number}\s", ws.title):
            return ws
    raise KeyError(f"Sheet {number} not found. Sheets: {wb.sheetnames}")


def parse_sheet(ws, geo_level: str, measure: str):
    rows = ws.iter_rows(values_only=True)
    header = {}
    for idx, row in enumerate(rows, start=1):
        if idx in (MONTH_ROW, YEAR_ROW):
            header[idx] = row
        if idx == YEAR_ROW:
            break
    qcols = quarter_columns(header[MONTH_ROW], header[YEAR_ROW])

    for idx, row in enumerate(rows, start=YEAR_ROW + 1):
        if idx < FIRST_DATA_ROW or row[AREA_COL] in (None, "") or row[DWELLING_COL] in (None, ""):
            continue
        area_name, area_label, area_pc = parse_area(row[AREA_COL], geo_level)
        dwelling = str(row[DWELLING_COL]).strip()
        dtype, beds = parse_dwelling(dwelling)
        for col, qend in qcols.items():
            v = row[col] if col < len(row) else None
            if v is None or v == "":          # suppressed / no data (suburb sheets use '')
                continue
            if not isinstance(v, (int, float)):
                raise ValueError(f"{ws.title!r} row {idx}: non-numeric value {v!r}")
            yield Record(geo_level, area_name, area_label, area_pc, dwelling, dtype, beds,
                         qend, measure, float(v))


def parse_contents(wb) -> dict[str, str]:
    """Topic -> 'Latest time period' (e.g. 'Sep Qtr 2026') from the Contents sheet."""
    out = {}
    for row in wb["Contents"].iter_rows(values_only=True):
        if isinstance(row[1], int) and isinstance(row[2], str) and isinstance(row[5], str):
            out[row[1]] = row[5]
    return out


def parse_workbook(path: Path) -> list[Record]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    latest = parse_contents(wb)
    records: list[Record] = []
    for number, (geo, measure) in SHEETS.items():
        ws = find_sheet(wb, number)
        recs = list(parse_sheet(ws, geo, measure))
        if not recs:
            raise ValueError(f"Sheet {ws.title!r} produced no records")
        max_q = max(r.quarter_end for r in recs)
        expected = latest.get(number)
        if expected:
            mon, _, yr = expected.split()
            if (max_q.year, max_q.month) != (int(yr), QUARTER_END[mon][0]):
                log.warning("%s: latest data %s but Contents says %s", ws.title.strip(), max_q, expected)
        log.info("%-18s %-11s %-9s %8d values, latest quarter %s",
                 ws.title.strip(), measure, geo, len(recs), max_q)
        records.extend(recs)
    wb.close()
    return records


def quality_checks(records: list[Record]) -> list[str]:
    """Return a list of warnings; raise on hard failures."""
    warnings = []
    keys = set()
    for r in records:
        k = (r.geo_level, r.area_name, r.dwelling, r.quarter_end, r.measure)
        if k in keys:
            raise ValueError(f"Duplicate key {k}")
        keys.add(k)
    rents = [r for r in records if r.measure == "median_rent"]
    odd = [r for r in rents if not 30 <= r.value <= 5000]
    if odd:
        warnings.append(f"{len(odd)} median rents outside $30-$5000/week, e.g. {odd[0]}")
    neg = [r for r in records if r.value < 0]
    if neg:
        raise ValueError(f"{len(neg)} negative values, e.g. {neg[0]}")
    return warnings


# --------------------------------------------------------------------------- #
# IO
# --------------------------------------------------------------------------- #
def download(dest: Path, url: str = RTA_URL) -> Path:
    import requests
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=120, headers={"User-Agent": "rent-pipeline/1.0"})
    resp.raise_for_status()
    if not resp.content.startswith(b"PK"):
        raise ValueError("Downloaded file is not an .xlsx (RTA may have moved the link)")
    dest.write_bytes(resp.content)
    log.info("downloaded %s (%.1f MB)", dest, len(resp.content) / 1e6)
    return dest


def write_csv(records: list[Record], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(r.as_row() for r in records)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def already_loaded(dsn: str, sha: str, geo: list[str] | None) -> bool:
    """True if the last successful RTA load used this exact workbook and geo filter."""
    import psycopg

    with psycopg.connect(dsn) as conn:
        if conn.execute("SELECT to_regclass('raw.ingest_log')").fetchone()[0] is None:
            return False
        row = conn.execute(
            "SELECT file_sha256, detail->'geo' FROM raw.ingest_log WHERE source = 'rta' "
            "ORDER BY loaded_at DESC LIMIT 1").fetchone()
    return bool(row) and row[0] == sha and row[1] == (sorted(geo) if geo else None)


def load_to_postgres(dsn: str, records: list[Record], source_file: str,
                     sha: str | None = None, geo: list[str] | None = None) -> int:
    import psycopg

    cols = COLUMNS + ["source_file"]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE raw.rta_bond_stats")
        with cur.copy(f"COPY raw.rta_bond_stats ({', '.join(cols)}) FROM STDIN") as cp:
            for r in records:
                cp.write_row(r.as_row() + [source_file])
        if cur.execute("SELECT to_regclass('raw.ingest_log')").fetchone()[0] is not None:
            cur.execute(
                "INSERT INTO raw.ingest_log (source, rows_loaded, file_sha256, detail) VALUES ('rta', %s, %s, %s)",
                (len(records), sha, json.dumps({"file": source_file, "geo": sorted(geo) if geo else None})))
        conn.commit()   # truncate + load + log succeed or fail together
    return len(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--download", action="store_true", help="download the latest workbook first")
    parser.add_argument("--skip-db", action="store_true")
    parser.add_argument("--csv-out", type=Path, help="also write the long table to CSV")
    parser.add_argument("--geo", help="comma-separated geo levels to load (postcode,suburb,lga,state); "
                                      "default all. The dbt models only use suburb and state.")
    parser.add_argument("--if-changed", action="store_true",
                        help="skip the database load if this exact workbook (and --geo) was already loaded")
    args = parser.parse_args(argv)
    geo = [g.strip() for g in args.geo.split(",")] if args.geo else None
    if geo and not set(geo) <= {"postcode", "suburb", "lga", "state"}:
        parser.error(f"unknown geo level in --geo {args.geo}")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    if args.download:
        download(args.file)
    if not args.file.exists():
        log.error("Workbook not found: %s (download it from %s)", args.file, RTA_URL)
        return 1

    sha = file_sha256(args.file)
    if args.if_changed and not args.skip_db and already_loaded(os.environ["DATABASE_URL"], sha, geo):
        log.info("workbook unchanged since last load (sha256 %s...); nothing to do", sha[:12])
        return 0

    records = parse_workbook(args.file)          # always parse everything: the checks cover all sheets
    for w in quality_checks(records):
        log.warning(w)
    log.info("parsed %d records", len(records))
    if geo:
        records = [r for r in records if r.geo_level in geo]
        log.info("keeping %d records for geo levels %s", len(records), ",".join(geo))

    if args.csv_out:
        write_csv(records, args.csv_out)
        log.info("wrote %s", args.csv_out)
    if not args.skip_db:
        n = load_to_postgres(os.environ["DATABASE_URL"], records, args.file.name, sha=sha, geo=geo)
        log.info("loaded %d rows into raw.rta_bond_stats", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
