"""RTA parser tests.

Unit tests use a small synthetic workbook that copies the real layout and its quirks
(trailing-space sheet name, '' for blanks, 'West End (4101)' names). If the real
workbook is present in data/raw/rta/, an extra test checks known values from it.
"""
import os
from datetime import date

import openpyxl
import pytest

import ingest_rta as rta

MONTHS = ["Mar", "Jun", "Sep", "Dec"]


def add_sheet(wb, title, area_header, rows, start=(2025, 0), n_quarters=4):
    ws = wb.create_sheet(title)
    ws.cell(1, 2, "Contents")
    ws.cell(5, 3, area_header); ws.cell(5, 4, "Dwelling")
    y, m = start
    for i in range(n_quarters):
        ws.cell(6, 5 + i, MONTHS[m]); ws.cell(7, 5 + i, y)
        m += 1
        if m == 4:
            y, m = y + 1, 0
    for r, (area, dwelling, *vals) in enumerate(rows, start=9):
        ws.cell(r, 3, area); ws.cell(r, 4, dwelling)
        for c, v in enumerate(vals, start=5):
            ws.cell(r, c, v)


@pytest.fixture
def workbook(tmp_path):
    wb = openpyxl.Workbook()
    contents = wb.active
    contents.title = "Contents"
    for n in range(1, 13):
        contents.cell(6 + n, 2, n); contents.cell(6 + n, 3, f"topic {n}"); contents.cell(6 + n, 6, "Dec Qtr 2025")
    headers = {"postcode": "Postcode", "suburb": "Suburb", "lga": "Local Government Area", "state": "State"}
    for n, (geo, measure) in rta.SHEETS.items():
        title = f"{n} {geo}-{measure}" + (" " if n == 7 else "")     # mimic '7 lga-rents '
        if geo == "postcode":
            rows = [(4000, "Flat 1", 430, None, 440, 450), (4066, "House 3", 700, 710, 720, 730)]
        elif geo == "suburb":
            rows = [("Toowong", "Flat 2", "", 600, 610, 620),
                    ("West End (4101)", "All dwellings", 650.5, 660, "", 680)]
        elif geo == "lga":
            rows = [("Brisbane (C)", "Townhouse 3", 690, 700, 710, 720)]
        else:
            rows = [("Queensland", "Rooming Accommodation", 380, 385, 390, 395)]
        add_sheet(wb, title, headers[geo], rows)
    p = tmp_path / "rta.xlsx"
    wb.save(p)
    return p


def test_parse_long_format(workbook):
    recs = rta.parse_workbook(workbook)
    by_key = {(r.geo_level, r.area_name, r.dwelling, r.quarter_end, r.measure): r for r in recs}

    r = by_key[("postcode", "4000", "Flat 1", date(2025, 3, 31), "median_rent")]
    assert (r.value, r.dwelling_type, r.bedrooms, r.area_postcode) == (430, "Flat", 1, "4000")

    # blanks ('' and None) are skipped, not loaded as 0
    assert ("suburb", "Toowong", "Flat 2", date(2025, 3, 31), "median_rent") not in by_key
    assert ("postcode", "4000", "Flat 1", date(2025, 6, 30), "median_rent") not in by_key

    we = by_key[("suburb", "West End (4101)", "All dwellings", date(2025, 3, 31), "median_rent")]
    assert (we.area_label, we.area_postcode, we.dwelling_type, we.bedrooms, we.value) == (
        "West End", "4101", "All", None, 650.5)

    state = by_key[("state", "Queensland", "Rooming Accommodation", date(2025, 12, 31), "bonds_held")]
    assert state.dwelling_type == "Rooming Accommodation" and state.bedrooms is None

    assert {r.geo_level for r in recs} == {"postcode", "suburb", "lga", "state"}
    assert rta.quality_checks(recs) == []


def test_header_change_fails_loudly():
    with pytest.raises(ValueError, match="Unexpected quarter header"):
        rta.quarter_columns((None,) * 4 + ("Q1",), (None,) * 4 + (2025,))


def test_dwelling_and_area_parsing():
    assert rta.parse_dwelling("Townhouse 2") == ("Townhouse", 2)
    assert rta.parse_dwelling("All dwellings") == ("All", None)
    assert rta.parse_dwelling("Other") == ("Other", None)
    assert rta.parse_area(4066, "postcode") == ("4066", "4066", "4066")
    assert rta.parse_area("The Gap (4061)", "suburb") == ("The Gap (4061)", "The Gap", "4061")
    assert rta.parse_area("Toowong", "suburb") == ("Toowong", "Toowong", None)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")
def test_load_is_full_refresh(workbook):
    import psycopg

    dsn = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        conn.execute(open(rta.ROOT / "sql" / "002_rta_schema.sql").read())
    recs = rta.parse_workbook(workbook)
    rta.load_to_postgres(dsn, recs, "test.xlsx")
    rta.load_to_postgres(dsn, recs, "test.xlsx")          # reload must not duplicate
    with psycopg.connect(dsn) as conn:
        n = conn.execute("SELECT count(*) FROM raw.rta_bond_stats").fetchone()[0]
        yoy = conn.execute("""SELECT rent_yoy_pct FROM raw.v_rta_quarterly
                              WHERE area_name='4066' AND quarter_end='2025-12-31'""").fetchone()
    assert n == len(recs)
    assert yoy == (None,)   # only 4 quarters of history -> no prior-year value


REAL = rta.DEFAULT_XLSX


@pytest.mark.skipif(not REAL.exists(), reason="real RTA workbook not downloaded")
def test_real_workbook_known_values():
    recs = rta.parse_workbook(REAL)
    v = {(r.geo_level, r.area_name, r.dwelling, r.quarter_end, r.measure): r.value for r in recs}
    assert v[("postcode", "4000", "Flat 1", date(2012, 3, 31), "median_rent")] == 430
    assert v[("suburb", "Toowong", "Flat 1", date(2017, 9, 30), "median_rent")] == 390
    rta.quality_checks(recs)   # raises on duplicates/negatives; range warnings are allowed


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")
def test_geo_filter_and_if_changed(workbook, monkeypatch):
    """--geo keeps only the requested levels; --if-changed skips an identical second load."""
    import psycopg

    dsn = os.environ["TEST_DATABASE_URL"]
    # Set both: database_url() prefers DATABASE_URL_UNPOOLED, and load_env() would
    # otherwise fill it from .env.local (a Neon URL) and load the test data there.
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", dsn)
    with psycopg.connect(dsn) as conn:
        for f in ("002_rta_schema.sql", "003_ingest_log.sql"):
            conn.execute(open(rta.ROOT / "sql" / f).read())
        conn.execute("TRUNCATE raw.ingest_log")

    args = ["--file", str(workbook), "--geo", "suburb,state", "--if-changed"]
    assert rta.main(args) == 0
    assert rta.main(args) == 0          # same file + same geo -> skipped

    with psycopg.connect(dsn) as conn:
        levels = {r[0] for r in conn.execute("SELECT DISTINCT geo_level FROM raw.rta_bond_stats")}
        log_rows = conn.execute("SELECT count(*) FROM raw.ingest_log WHERE source = 'rta'").fetchone()[0]
    assert levels == {"suburb", "state"}
    assert log_rows == 1                # only the first run loaded

    assert rta.main(["--file", str(workbook), "--if-changed"]) == 0   # different geo -> reloads
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM raw.ingest_log WHERE source = 'rta'").fetchone()[0] == 2


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")
def test_audit_refuses_shrinking_or_older_workbook(workbook):
    """A load that loses >10% of a level's rows, or moves its latest quarter back, is refused
    before the truncate, so the table keeps its current contents. --force overrides."""
    import psycopg

    dsn = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        conn.execute(open(rta.ROOT / "sql" / "002_rta_schema.sql").read())
    recs = rta.parse_workbook(workbook)
    rta.load_to_postgres(dsn, recs, "full.xlsx", force=True)

    def count():
        with psycopg.connect(dsn) as conn:
            return conn.execute("SELECT count(*) FROM raw.rta_bond_stats").fetchone()[0]

    latest = max(r.quarter_end for r in recs)
    older = [r for r in recs if r.quarter_end < latest]          # last quarter missing
    half = [r for i, r in enumerate(recs) if r.geo_level != "postcode" or i % 2]   # postcode level halved

    for bad, why in ((older, "older than the loaded"), (half, "postcode:")):
        with pytest.raises(rta.AuditError, match=why):
            rta.load_to_postgres(dsn, bad, "bad.xlsx")
        assert count() == len(recs)                              # nothing changed

    only_state = [r for r in recs if r.geo_level == "state"]     # dropping levels on purpose is fine
    assert rta.load_to_postgres(dsn, only_state, "state.xlsx") == len(only_state)
    assert rta.load_to_postgres(dsn, older, "forced.xlsx", force=True) == len(older)
