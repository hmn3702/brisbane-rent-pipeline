"""
Build the public dashboard (GitHub Pages) from the exported marts.

    python scripts/export_marts.py          # writes powerbi/data/*.csv
    python scripts/build_site.py            # writes _site/index.html + _site/data.json
    python -m http.server -d _site 8000     # preview on http://localhost:8000

Only RTA data is published. Domain listings stay off the public page until real (not synthetic)
listings exist, so nothing on it is demo data.
"""
import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DWELLINGS = ["All dwellings", "Flat 1", "Flat 2", "Flat 3", "Townhouse 2", "Townhouse 3",
             "House 2", "House 3", "House 4", "Other"]


def num(v, nd=1):
    if v in ("", None):
        return None
    f = float(v)
    return int(round(f)) if nd == 0 else round(f, nd)


def read(data_dir: Path, name: str) -> list[dict]:
    with open(data_dir / f"{name}.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build(data_dir: Path) -> dict:
    trend = read(data_dir, "mart_rta_suburb_trend")
    latest = read(data_dir, "mart_rta_suburb_latest")
    season = read(data_dir, "mart_rta_seasonality")
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))

    quarters = sorted({r["quarter_end"] for r in trend})
    qi = {q: i for i, q in enumerate(quarters)}
    names = sorted({r["area_name"] for r in trend} | {r["area_name"] for r in latest})
    si = {n: i for i, n in enumerate(names)}
    qld = {d: [None] * len(quarters) for d in DWELLINGS}
    rent = {d: {} for d in DWELLINGS}
    for r in trend:
        d = r["dwelling"]
        if d not in rent:
            continue
        i = qi[r["quarter_end"]]
        qld[d][i] = num(r["qld_median_weekly_rent"], 0)
        rent[d].setdefault(si[r["area_name"]], [None] * len(quarters))[i] = num(r["median_weekly_rent"], 0)

    lat = defaultdict(list)
    for r in latest:
        if r["dwelling"] in DWELLINGS:
            lat[r["dwelling"]].append([si[r["area_name"]], num(r["median_weekly_rent"], 0), num(r["rent_yoy_pct"]),
                                       num(r["rent_5y_pct"]), num(r["new_bonds"], 0), num(r["rent_rank_qld"], 0)])

    s_state, s_sub = defaultdict(lambda: [None] * 4), defaultdict(dict)
    for r in season:
        d = r["dwelling"]
        if d not in DWELLINGS:
            continue
        q = int(r["quarter_of_year"]) - 1
        row = [num(r["rent_dev_pct"], 2), num(r["rent_t_stat"]), r["is_rent_significant"] == "true",
               num(r["bonds_dev_pct"]), num(r["avg_new_bonds"], 0), num(r["n_years_rent"], 0),
               num(r["n_years_bonds"], 0), num(r["rent_dev_pct_before_2020"], 2), num(r["rent_dev_pct_2020_on"], 2)]
        if r["geo_level"] == "state":
            s_state[d][q] = row
        elif r["area_name"] in si:
            s_sub[d].setdefault(si[r["area_name"]], [None] * 4)[q] = row

    return {
        "meta": {"exported_at": manifest.get("exported_at"), "latest_quarter": manifest.get("rta_latest_quarter"),
                 "season_fields": ["rent_dev", "t", "significant", "bonds_dev", "avg_new_bonds", "n_years_rent",
                                   "n_years_bonds", "rent_dev_before_2020", "rent_dev_2020_on"],
                 "latest_fields": ["suburb", "rent", "yoy", "y5", "new_bonds", "rank"]},
        "quarters": quarters,
        "dwellings": DWELLINGS,
        "suburbs": names,   # area_name: unique, and already carries a postcode where two suburbs share a name
        "qld": qld,
        "rent": rent,
        "latest": lat,
        "season_state": s_state,
        "season_suburb": s_sub,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=ROOT / "powerbi" / "data")
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--dbt-docs", type=Path, help="dbt target/static_index.html to publish at /dbt/")
    args = p.parse_args(argv)

    data = build(args.data)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "data.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    shutil.copy(ROOT / "web" / "index.html", args.out / "index.html")
    (args.out / ".nojekyll").write_text("")
    if args.dbt_docs:
        (args.out / "dbt").mkdir(exist_ok=True)
        shutil.copy(args.dbt_docs, args.out / "dbt" / "index.html")
    size = (args.out / "data.json").stat().st_size
    print(f"site -> {args.out}  data.json {size / 1e6:.2f} MB, {len(data['suburbs'])} suburbs, "
          f"{len(data['quarters'])} quarters to {data['meta']['latest_quarter']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
