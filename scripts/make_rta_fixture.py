"""
Build a small, deterministic workbook in the RTA bond-statistics layout, for CI.

CI must not depend on the RTA website being up, and the real workbook is not committed.
This fixture has the same 12 sheets, headers and quirks as the real file (a trailing space
in one sheet name, '' for suppressed suburb cells, a duplicate suburb name carrying its
postcode), so CI also exercises ingest_rta.py's parser end to end.

Every suburb in config/suburbs.csv is included, so the dbt test
assert_tracked_suburbs_exist_in_rta passes. The numbers are SYNTHETIC.

    python scripts/make_rta_fixture.py data/raw/rta/rta-bond-statistics.xlsx
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
MONTHS = ["Mar", "Jun", "Sep", "Dec"]
FIRST, LAST = (2020, 2), (2026, 2)          # Sep Qtr 2020 .. Sep Qtr 2026 (index into MONTHS)
RENT_DWELLINGS = ["Flat 1", "Flat 2", "Flat 3", "House 2", "House 3", "House 4",
                  "Townhouse 2", "Townhouse 3", "All dwellings"]
BOND_DWELLINGS = RENT_DWELLINGS[:-1] + ["Other", "All dwellings"]
BASE = {"Flat 1": 430, "Flat 2": 560, "Flat 3": 700, "House 2": 520, "House 3": 600,
        "House 4": 720, "Townhouse 2": 560, "Townhouse 3": 640, "All dwellings": 560}
SHEETS = [  # (number, sheet title, area header, geo)
    (1, "1 pc-rents", "Postcode", "postcode"), (2, "2 pc-new-bonds", "Postcode", "postcode"),
    (3, "3 pc-all-bonds", "Postcode", "postcode"), (4, "4 sub-rents", "Suburb", "suburb"),
    (5, "5 sub-new-bonds", "Suburb", "suburb"), (6, "6 sub-all-bonds", "Suburb", "suburb"),
    (7, "7 lga-rents ", "Local Government Area", "lga"),          # trailing space, as in the real file
    (8, "8 lga-new-bonds", "Local Government Area", "lga"), (9, "9 lga-all-bonds", "Local Government Area", "lga"),
    (10, "10 qld-rents", "State", "state"), (11, "11 qld-new-bonds", "State", "state"),
    (12, "12 qld-all-bonds", "State", "state"),
]


def quarters():
    y, m = FIRST
    while (y, m) <= LAST:
        yield y, m
        m += 1
        if m == 4:
            y, m = y + 1, 0


def areas(geo: str) -> list[str | int]:
    tracked = [r["rta_suburb"] for r in csv.DictReader(open(ROOT / "config" / "suburbs.csv"))]
    if geo == "suburb":
        return sorted(set(tracked) | {"Ascot", "West End (4810)", "Paddington"})
    if geo == "postcode":
        return sorted({int(r["postcode"]) for r in csv.DictReader(open(ROOT / "config" / "suburbs.csv"))})
    return ["Brisbane (C)"] if geo == "lga" else ["Queensland"]


def build(path: Path, seed: int = 7) -> Path:
    rng = random.Random(seed)
    qs = list(quarters())
    wb = openpyxl.Workbook()
    contents = wb.active
    contents.title = "Contents"
    contents.cell(2, 2, "Bond statistics data (SYNTHETIC CI FIXTURE)")
    contents.cell(6, 3, "Topic")
    last_label = f"{MONTHS[LAST[1]]} Qtr {LAST[0]}"
    for n, title, _, _ in SHEETS:
        contents.cell(6 + n, 2, n)
        contents.cell(6 + n, 3, title.strip())
        contents.cell(6 + n, 6, last_label)

    factor: dict[str | int, float] = {}
    for n, title, header, geo in SHEETS:
        ws = wb.create_sheet(title)
        ws.cell(1, 2, "Contents")
        ws.cell(5, 3, header)
        ws.cell(5, 4, "Dwelling")
        for i, (y, m) in enumerate(qs):
            ws.cell(6, 5 + i, MONTHS[m])
            ws.cell(7, 5 + i, y)
        measure = "rents" if "rents" in title else ("new" if "new-bonds" in title else "held")
        dwellings = RENT_DWELLINGS if measure == "rents" else BOND_DWELLINGS
        r = 9
        for area in areas(geo):
            f = factor.setdefault(area, rng.uniform(0.85, 1.35))
            for d in dwellings:
                ws.cell(r, 3, area)
                ws.cell(r, 4, d)
                for i, (y, m) in enumerate(qs):
                    growth = 1.06 ** (i / 4)                      # ~6% a year
                    season = 1.02 if m == 0 else 1.0              # a little March-quarter bump
                    if measure == "rents":
                        v = round(BASE[d] * f * growth * season * rng.uniform(0.97, 1.03) / 5) * 5
                        suppressed = geo == "suburb" and d.startswith("Townhouse") and rng.random() < 0.3
                        v = "" if suppressed else (v if geo != "postcode" or rng.random() > 0.1 else None)
                    else:
                        base = 600 if d == "All dwellings" else (300 if d == "Other" else 40)
                        v = int(base * f * rng.uniform(0.8, 1.2)) * (10 if measure == "held" else 1)
                    ws.cell(r, 5 + i, v)
                r += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "raw" / "rta" / "rta-bond-statistics.xlsx"
    print("wrote", build(out))
