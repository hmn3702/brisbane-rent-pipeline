"""
Generate the Power BI Project (PBIP) for the Brisbane rent dashboard:

    powerbi/pbip/RentDashboard.pbip
    powerbi/pbip/RentDashboard.SemanticModel/   (TMDL: tables, relationships, measures)
    powerbi/pbip/RentDashboard.Report/          (PBIR: 4 pages of visuals)

Everything is text, so the dashboard lives in git and can be regenerated after model changes.
Open RentDashboard.pbip in Power BI Desktop, then Home > Refresh to load the CSVs.

    python powerbi/build_pbip.py [--data-folder "E:\\path\\to\\powerbi\\data"]
"""
from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "pbip"
NAME = "RentDashboard"
DEFAULT_DATA_FOLDER = r"E:\project\QLD-rent-analysis\rent-pipeline\powerbi\data"

ASKING = "#E07B39"     # Domain / asking rents
SIGNED = "#1F6FB2"     # RTA / signed rents
NEUTRAL = "#9CA3AF"    # Queensland benchmark
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"


def tag() -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"rentdash/{next(_counter)}"))


def _count():
    i = 0
    while True:
        i += 1
        yield i


_counter = _count()


def q(name: str) -> str:
    """Quote a TMDL/DAX object name when needed."""
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


# =============================================================================
# Semantic model
# =============================================================================
CSV_TABLES = {
    # table: (csv file, [(column, tmdl dataType, M type, hidden, extra props)])
    "Gap": ("mart_rent_gap_suburb_quarter.csv", [
        ("suburb", "string", "type text", False, {}),
        ("rta_suburb", "string", "type text", True, {}),
        ("quarter_end", "dateTime", "type date", True, {}),
        ("dwelling", "string", "type text", True, {}),
        ("n_new_listings", "int64", "Int64.Type", False, {}),
        ("median_asking_rent", "double", "type number", False, {}),
        ("rta_quarter_end", "dateTime", "type date", False, {}),
        ("rta_quarters_behind", "int64", "Int64.Type", False, {}),
        ("median_signed_rent", "double", "type number", False, {}),
        ("rta_new_bonds", "double", "type number", False, {}),
        ("gap_dollars", "double", "type number", False, {}),
        ("gap_pct", "double", "type number", False, {}),
        ("is_low_sample", "boolean", "type logical", False, {}),
        ("gap_pct_mix_adjusted", "double", "type number", False, {}),
    ]),
    "RtaLatest": ("mart_rta_suburb_latest.csv", [
        ("area_name", "string", "type text", True, {}),
        ("suburb", "string", "type text", False, {}),
        ("area_postcode", "string", "type text", False, {}),
        ("location_label", "string", "type text", False, {}),
        ("dwelling", "string", "type text", True, {}),
        ("quarter_end", "dateTime", "type date", False, {}),
        ("median_weekly_rent", "double", "type number", False, {}),
        ("median_weekly_rent_prev_year", "double", "type number", False, {}),
        ("rent_yoy_pct", "double", "type number", False, {}),
        ("median_weekly_rent_5y_ago", "double", "type number", False, {}),
        ("rent_5y_pct", "double", "type number", False, {}),
        ("new_bonds", "double", "type number", False, {}),
        ("bonds_held", "double", "type number", False, {}),
        ("rent_rank_qld", "int64", "Int64.Type", False, {}),
        ("n_suburbs_ranked", "int64", "Int64.Type", False, {}),
        ("is_tracked", "boolean", "type logical", False, {}),
    ]),
    "RtaTrend": ("mart_rta_suburb_trend.csv", [
        ("area_name", "string", "type text", True, {}),
        ("suburb", "string", "type text", False, {}),
        ("area_postcode", "string", "type text", False, {}),
        ("location_label", "string", "type text", False, {}),
        ("dwelling", "string", "type text", True, {}),
        ("dwelling_type", "string", "type text", False, {}),
        ("bedrooms", "int64", "Int64.Type", False, {}),
        ("quarter_end", "dateTime", "type date", True, {}),
        ("median_weekly_rent", "double", "type number", False, {}),
        ("rent_yoy_pct", "double", "type number", False, {}),
        ("new_bonds", "double", "type number", False, {}),
        ("bonds_held", "double", "type number", False, {}),
        ("qld_median_weekly_rent", "double", "type number", False, {}),
        ("premium_vs_qld_pct", "double", "type number", False, {}),
        ("is_tracked", "boolean", "type logical", False, {}),
    ]),
    "Velocity": ("mart_listing_velocity_suburb_month.csv", [
        ("suburb", "string", "type text", False, {}),
        ("rta_suburb", "string", "type text", True, {}),
        ("month_start", "dateTime", "type date", False, {}),
        ("quarter_end", "dateTime", "type date", True, {}),
        ("dwelling", "string", "type text", True, {}),
        ("n_listings_closed", "int64", "Int64.Type", False, {}),
        ("median_days_on_market", "double", "type number", False, {}),
        ("pct_with_price_cut", "double", "type number", False, {}),
        ("median_final_asking_rent", "double", "type number", False, {}),
    ]),
}

DIM_TABLES = {
    "DimSuburb": ("""let
    Cols   = Table.SelectColumns(RtaTrend, {"area_name", "suburb", "area_postcode", "location_label", "is_tracked"}),
    Unique = Table.Distinct(Cols, {"area_name"})
in
    Unique""", [
        ("area_name", "string", False, {}),
        ("suburb", "string", False, {}),
        ("area_postcode", "string", False, {}),
        ("location_label", "string", False, {"dataCategory": "Place"}),
        ("is_tracked", "boolean", False, {}),
    ]),
    "DimDwelling": ("""let
    All    = List.Distinct(RtaTrend[dwelling] & Gap[dwelling] & Velocity[dwelling]),
    Base   = Table.FromList(All, Splitter.SplitByNothing(), type table [dwelling = text]),
    Order  = {"All dwellings", "Flat 1", "Flat 2", "Flat 3", "House 2", "House 3", "House 4", "Townhouse 2", "Townhouse 3", "Other"},
    Sorted = Table.AddColumn(Base, "dwelling_sort", each let i = List.PositionOf(Order, [dwelling]) in if i < 0 then 99 else i, Int64.Type),
    Typed  = Table.AddColumn(Sorted, "dwelling_type", each Text.BeforeDelimiter([dwelling], " "), type text)
in
    Typed""", [
        ("dwelling", "string", False, {"sortByColumn": "dwelling_sort"}),
        ("dwelling_sort", "int64", True, {}),
        ("dwelling_type", "string", False, {}),
    ]),
    "DimQuarter": ("""let
    All   = List.Distinct(RtaTrend[quarter_end] & Gap[quarter_end] & Velocity[quarter_end]),
    Base  = Table.FromList(All, Splitter.SplitByNothing(), type table [quarter_end = date]),
    Year  = Table.AddColumn(Base, "year", each Date.Year([quarter_end]), Int64.Type),
    Label = Table.AddColumn(Year, "quarter_label", each Date.ToText([quarter_end], [Format = "MMM", Culture = "en-AU"]) & " Qtr " & Text.From(Date.Year([quarter_end])), type text),
    Index = Table.AddColumn(Label, "quarter_index", each Date.Year([quarter_end]) * 4 + Date.QuarterOfYear([quarter_end]), Int64.Type)
in
    Index""", [
        ("quarter_end", "dateTime", False, {}),
        ("year", "int64", False, {}),
        ("quarter_label", "string", False, {"sortByColumn": "quarter_index"}),
        ("quarter_index", "int64", True, {}),
    ]),
}

RELATIONSHIPS = [  # (many side, one side)
    ("RtaTrend", "area_name", "DimSuburb", "area_name"),
    ("RtaLatest", "area_name", "DimSuburb", "area_name"),
    ("Gap", "rta_suburb", "DimSuburb", "area_name"),
    ("Velocity", "rta_suburb", "DimSuburb", "area_name"),
    ("RtaTrend", "dwelling", "DimDwelling", "dwelling"),
    ("RtaLatest", "dwelling", "DimDwelling", "dwelling"),
    ("Gap", "dwelling", "DimDwelling", "dwelling"),
    ("Velocity", "dwelling", "DimDwelling", "dwelling"),
    ("RtaTrend", "quarter_end", "DimQuarter", "quarter_end"),
    ("Gap", "quarter_end", "DimQuarter", "quarter_end"),
    ("Velocity", "quarter_end", "DimQuarter", "quarter_end"),
]

RENT, PCT, INT, DAYS = r"\$#,0", "0.0%;-0.0%;0.0%", "#,0", "0.0"


def rows(table: str, mode: str = "only_all", var: str = "_r", base: str | None = None, extra: str = "") -> str:
    """DAX VAR block defining table variable `var` that never mixes 'All dwellings' with per-dwelling rows.
    (DAX IF cannot return a table, so the choice is made with FILTER conditions on a captured VALUES list.)
      only_all : 'All dwellings' in the dwelling filter (or no filter) -> only the 'All dwellings' rows
      detail   : 'All dwellings' in the filter -> every per-dwelling row, i.e. the mix behind the total
    `base` overrides the starting table (e.g. CALCULATETABLE(..., REMOVEFILTERS(DimSuburb)));
    `extra` is an additional row condition."""
    t = table
    src = base or t
    cond = f" && ( {extra} )" if extra else ""
    pre = (f'VAR {var}_sel = VALUES ( DimDwelling[dwelling] )\n'
           f'VAR {var}_all = "All dwellings" IN {var}_sel\n')
    if mode == "only_all":
        return pre + (f'VAR {var} = FILTER ( {src}, IF ( {var}_all, {t}[dwelling] = "All dwellings", TRUE () ){cond} )\n')
    base_all = base.replace(")", ", REMOVEFILTERS ( DimDwelling ) )", 1) if base else \
        f"CALCULATETABLE ( {t}, REMOVEFILTERS ( DimDwelling ) )"
    return pre + (f'VAR {var} = FILTER ( {base_all}, {t}[dwelling] <> "All dwellings" '
                  f'&& ( {var}_all || {t}[dwelling] IN {var}_sel ){cond} )\n')


def weighted(t: str, value: str, weight: str, prelude: str, var: str = "_r", scale: int = 1) -> str:
    """Published median for one row, weighted average of medians (by `weight`) for several.
    scale=100 turns a percentage column (8.5) into a fraction (0.085) for % formatting."""
    div = "" if scale == 1 else f" / {scale}"
    return prelude + f"""VAR _t = FILTER ( {var}, NOT ISBLANK ( {t}[{value}] ) )
RETURN
    IF (
        COUNTROWS ( _t ) = 1,
        MAXX ( _t, {t}[{value}] ){div},
        DIVIDE ( SUMX ( _t, {t}[{value}] * {t}[{weight}] ), SUMX ( _t, {t}[{weight}] ) ){div}
    )"""


LAG = "Gap[rta_quarters_behind] <= [Max RTA Lag Value]"
LATEST_Q = "VAR _q = [Latest RTA Quarter]\nRETURN\n    CALCULATE ( {m}, REMOVEFILTERS ( DimQuarter ), DimQuarter[quarter_end] = _q )"
RELIABLE = "RtaLatest[new_bonds] >= 30"

MEASURES = [
    # (name, folder, format, description, expression)
    ("Max RTA Lag Value", "Parameters", INT, "Selected maximum RTA lag (quarters); 0 = like-for-like.",
     "SELECTEDVALUE ( 'Max RTA Lag'[Max RTA Lag], 0 )"),
    ("Latest RTA Quarter", "Parameters", "yyyy-mm-dd", "Latest quarter in the RTA data.",
     "CALCULATE ( MAX ( RtaLatest[quarter_end] ), REMOVEFILTERS () )"),

    # ---- RTA signed rents
    ("Signed Rent", "RTA", RENT,
     "Median weekly rent of new tenancies (RTA). Weighted average of medians by new bonds when several rows are in context.",
     weighted("RtaTrend", "median_weekly_rent", "new_bonds", rows("RtaTrend"))),
    ("Signed Rent LY", "RTA", RENT, "Signed rent for the same quarter one year earlier.",
     "VAR _q = MAX ( DimQuarter[quarter_end] )\nRETURN\n    CALCULATE ( [Signed Rent], REMOVEFILTERS ( DimQuarter ), DimQuarter[quarter_end] = EOMONTH ( _q, -12 ) )"),
    ("Signed Rent YoY %", "RTA", PCT, "Year-on-year change in signed rent (RTA advises YoY, not QoQ).",
     "DIVIDE ( [Signed Rent] - [Signed Rent LY], [Signed Rent LY] )"),
    ("QLD Median Rent", "RTA", RENT, "Queensland-wide median for the quarter and dwelling in context.",
     rows("RtaTrend", base="CALCULATETABLE ( RtaTrend, REMOVEFILTERS ( DimSuburb ) )") + """RETURN
    IF (
        HASONEVALUE ( DimQuarter[quarter_end] ) && COUNTROWS ( DISTINCT ( SELECTCOLUMNS ( _r, "d", RtaTrend[dwelling] ) ) ) = 1,
        MAXX ( _r, RtaTrend[qld_median_weekly_rent] )
    )"""),
    ("QLD Median Rent LY", "RTA", RENT, "Queensland median one year earlier.",
     "VAR _q = MAX ( DimQuarter[quarter_end] )\nRETURN\n    CALCULATE ( [QLD Median Rent], REMOVEFILTERS ( DimQuarter ), DimQuarter[quarter_end] = EOMONTH ( _q, -12 ) )"),
    ("Premium vs QLD %", "RTA", PCT, "Signed rent relative to the Queensland median.",
     "DIVIDE ( [Signed Rent], [QLD Median Rent] ) - 1"),
    ("New Bonds", "RTA", INT, "New tenancies signed (no double count of 'All dwellings').",
     rows("RtaTrend") + "RETURN SUMX ( _r, RtaTrend[new_bonds] )"),
    ("Signed Rent (latest)", "RTA latest", RENT, "Signed rent in the latest RTA quarter.",
     LATEST_Q.format(m="[Signed Rent]")),
    ("Signed Rent YoY % (latest)", "RTA latest", PCT, "YoY change in the latest RTA quarter.",
     LATEST_Q.format(m="[Signed Rent YoY %]")),
    ("Premium vs QLD % (latest)", "RTA latest", PCT, "Premium over Queensland in the latest quarter.",
     LATEST_Q.format(m="[Premium vs QLD %]")),
    ("QLD Median Rent (latest)", "RTA latest", RENT, "Queensland median in the latest quarter.",
     LATEST_Q.format(m="[QLD Median Rent]")),
    ("QLD Median YoY % (latest)", "RTA latest", PCT, "Queensland median YoY in the latest quarter.",
     LATEST_Q.format(m="DIVIDE ( [QLD Median Rent], [QLD Median Rent LY] ) - 1")),

    # ---- League table (RtaLatest); suburbs with < 30 new bonds are blanked to hide noisy medians
    ("Latest Rent", "League table", RENT, "Latest signed median (suburbs with >= 30 new bonds).",
     weighted("RtaLatest", "median_weekly_rent", "new_bonds", rows("RtaLatest", extra=RELIABLE))),
    ("Latest YoY %", "League table", PCT, "1-year change, suburbs with >= 30 new bonds.",
     weighted("RtaLatest", "rent_yoy_pct", "new_bonds", rows("RtaLatest", extra=RELIABLE), scale=100)),
    ("Latest 5y %", "League table", PCT, "5-year change, suburbs with >= 30 new bonds.",
     weighted("RtaLatest", "rent_5y_pct", "new_bonds", rows("RtaLatest", extra=RELIABLE), scale=100)),
    ("Latest New Bonds", "League table", INT, "New bonds in the latest quarter.",
     rows("RtaLatest") + "RETURN SUMX ( _r, RtaLatest[new_bonds] )"),
    ("QLD Rank", "League table", INT, "Rank among QLD suburbs by median rent (1 = most expensive).",
     rows("RtaLatest", extra=RELIABLE) + "RETURN IF ( COUNTROWS ( _r ) = 1, MAXX ( _r, RtaLatest[rent_rank_qld] ) )"),
    ("Suburbs Ranked", "League table", INT, "Suburbs with a reliable latest median (>= 30 new bonds).",
     rows("RtaLatest", extra=RELIABLE + " && NOT ISBLANK ( RtaLatest[median_weekly_rent] )") + "RETURN COUNTROWS ( _r )"),

    # ---- Domain vs RTA
    ("Asking Rent", "Gap", RENT, "Median asking rent of new Domain listings; weighted by listings when several rows.",
     weighted("Gap", "median_asking_rent", "n_new_listings", rows("Gap", extra=LAG))),
    ("Signed Rent (compared)", "Gap", RENT,
     "RTA signed rent of the quarter the asking rents are compared with (as-of join); weighted by bonds.",
     weighted("Gap", "median_signed_rent", "rta_new_bonds", rows("Gap", extra=LAG))),
    ("Gap %", "Gap", PCT,
     "Asking vs signed rent. With 'All dwellings' (or no dwelling filter) it is mix-adjusted: per-dwelling gaps "
     "weighted by RTA new bonds. For one suburb this equals gap_pct_mix_adjusted in the dbt mart.",
     rows("Gap", "detail", extra="NOT ISBLANK ( Gap[gap_pct] ) && " + LAG) + f"""RETURN
    IF (
        COUNTROWS ( _r ) = 1,
        MAXX ( _r, Gap[gap_pct] ) / 100,
        DIVIDE ( SUMX ( _r, Gap[gap_pct] * Gap[rta_new_bonds] ), SUMX ( _r, Gap[rta_new_bonds] ) ) / 100
    )"""),
    ("New Listings", "Gap", INT, "New Domain listings in the period.",
     rows("Gap", extra=LAG) + "RETURN SUMX ( _r, Gap[n_new_listings] )"),
    ("Low Sample Rows", "Gap", INT, "Cells resting on < 5 listings or < 10 RTA bonds.",
     f"COUNTROWS ( FILTER ( Gap, Gap[is_low_sample] && {LAG} ) ) + 0"),
    ("RTA Quarter Compared", "Gap", None, "Which RTA quarter the asking rents are compared with.",
     f'VAR _q = MAXX ( FILTER ( Gap, {LAG} ), Gap[rta_quarter_end] )\nRETURN IF ( ISBLANK ( _q ), "–", "vs RTA " & FORMAT ( _q, "mmm" ) & " Qtr " & YEAR ( _q ) )'),

    # ---- Leasing speed
    ("Listings Closed", "Velocity", INT, "Listings that left the market (leased or withdrawn).",
     rows("Velocity") + "RETURN SUMX ( _r, Velocity[n_listings_closed] )"),
    ("Days on Market", "Velocity", DAYS, "Median days on market; weighted average of medians when several rows.",
     weighted("Velocity", "median_days_on_market", "n_listings_closed", rows("Velocity"))),
    ("Price Cut %", "Velocity", PCT, "Share of closed listings that cut the asking price first.",
     rows("Velocity") + "RETURN DIVIDE ( SUMX ( _r, Velocity[pct_with_price_cut] * Velocity[n_listings_closed] ), SUMX ( _r, Velocity[n_listings_closed] ) ) / 100"),

    # ---- Labels
    ("Data Banner", "Labels", None, "Warns when Domain listings are synthetic.",
     'IF ( COUNTROWS ( Gap ) = 0, "RTA data only · Domain listings pending API access", '
     'IF ( SELECTEDVALUE ( Manifest[domain_data_is_synthetic], FALSE () ), "DEMO DATA · Domain listings are synthetic · RTA figures are real", "Live Domain snapshots + RTA bond data" ) )'),
    ("Data As Of", "Labels", None, "Data currency label.",
     '"RTA data to " & FORMAT ( SELECTEDVALUE ( Manifest[rta_latest_quarter] ), "mmm yyyy" ) & "  ·  exported " & LEFT ( SELECTEDVALUE ( Manifest[exported_at] ), 10 )'),
    ("Source Credit", "Labels", None, "Attribution.",
     '"Source: Residential Tenancies Authority (Qld), CC BY 4.0 · Domain listings"'),
]


def indent(text: str, n: int) -> str:
    return "\n".join(("\t" * n + line) if line.strip() else "" for line in text.splitlines())


def m_csv(csv: str, cols) -> str:
    types = ",\n        ".join(f'{{"{c}", {mt}}}' for c, _, mt, _, _ in cols)
    return f"""let
    Source  = Csv.Document(File.Contents(DataFolder & "\\{csv}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed   = Table.TransformColumnTypes(Headers, {{
        {types}}}, "en-US")
in
    Typed"""


def tmdl_column(name, dtype, hidden, extra, calculated=False) -> str:
    """Column of an import table; calculated=True for calculated-table columns ([Name] source)."""
    lines = [f"\tcolumn {q(name)}", f"\t\tdataType: {dtype}"]
    if dtype == "dateTime":
        lines.append("\t\tformatString: yyyy-mm-dd")
    if hidden:
        lines.append("\t\tisHidden")
    for k, v in extra.items():
        lines.append(f"\t\t{k}: {v}")
    lines += [f"\t\tlineageTag: {tag()}", "\t\tsummarizeBy: none"]
    if calculated:
        lines += ["\t\tisNameInferred", f"\t\tsourceColumn: [{name}]"]
    else:
        lines.append(f"\t\tsourceColumn: {name}")
    lines += ["", "\t\tannotation SummarizationSetBy = User"]
    if dtype == "dateTime":
        lines += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
    return "\n".join(lines) + "\n"


def tmdl_table(name: str, columns_tmdl: list[str], m_or_dax: str, kind: str = "m", hidden=False, extra="") -> str:
    head = [f"table {q(name)}"] + (["\tisHidden"] if hidden else []) + [f"\tlineageTag: {tag()}", ""]
    part = [f"\tpartition {q(name)} = {kind}", "\t\tmode: import", "\t\tsource =", indent(m_or_dax, 4), ""]
    tail = ["\tannotation PBI_ResultType = Table", ""] if kind == "m" else []
    return "\n".join(head) + extra + "\n".join(columns_tmdl) + "\n" + "\n".join(part) + "\n" + "\n".join(tail)


def build_model(data_folder: str) -> dict[str, str]:
    files: dict[str, str] = {}
    sm = f"{NAME}.SemanticModel"
    files[f"{sm}/definition.pbism"] = json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0", "settings": {}}, indent=2)
    files[f"{sm}/definition/database.tmdl"] = "database\n\tcompatibilityLevel: 1600\n"

    table_names = list(CSV_TABLES) + ["Manifest"] + list(DIM_TABLES) + ["Max RTA Lag", "_Measures"]
    files[f"{sm}/definition/model.tmdl"] = "\n".join([
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        "annotation PBI_QueryOrder = " + json.dumps(["DataFolder"] + list(CSV_TABLES) + ["Manifest"] + list(DIM_TABLES)),
        "",
    ] + [f"ref table {q(t)}" for t in table_names] + [""])

    files[f"{sm}/definition/expressions.tmdl"] = (
        f'expression DataFolder = "{data_folder}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {tag()}\n\n\tannotation PBI_ResultType = Text\n")

    for t, (csv, cols) in CSV_TABLES.items():
        cols_tmdl = [tmdl_column(c, d, h, e) for c, d, _, h, e in cols]
        files[f"{sm}/definition/tables/{t}.tmdl"] = tmdl_table(t, cols_tmdl, m_csv(csv, cols))

    manifest_m = """let
    Json = Json.Document(File.Contents(DataFolder & "\\manifest.json")),
    Row  = #table(
        type table [exported_at = text, domain_data_is_synthetic = logical, domain_synthetic_share = number, rta_latest_quarter = date],
        {{ Json[exported_at], Json[domain_data_is_synthetic], Json[domain_synthetic_share], Date.FromText(Json[rta_latest_quarter], "en-US") }})
in
    Row"""
    mcols = [tmdl_column("exported_at", "string", False, {}),
             tmdl_column("domain_data_is_synthetic", "boolean", False, {}),
             tmdl_column("domain_synthetic_share", "double", False, {}),
             tmdl_column("rta_latest_quarter", "dateTime", False, {})]
    files[f"{sm}/definition/tables/Manifest.tmdl"] = tmdl_table("Manifest", mcols, manifest_m, hidden=True)

    for t, (m, cols) in DIM_TABLES.items():
        cols_tmdl = [tmdl_column(c, d, h, e) for c, d, h, e in cols]
        files[f"{sm}/definition/tables/{t}.tmdl"] = tmdl_table(t, cols_tmdl, m)

    lag_col = tmdl_column("Max RTA Lag", "int64", False, {}, calculated=True)
    files[f"{sm}/definition/tables/Max RTA Lag.tmdl"] = tmdl_table(
        "Max RTA Lag", [lag_col], 'SELECTCOLUMNS ( GENERATESERIES ( 0, 2, 1 ), "Max RTA Lag", [Value] )', kind="calculated")

    mlines = []
    for name, folder, fmt, desc, expr in MEASURES:
        mlines.append(f"\t/// {desc}")
        mlines.append(f"\tmeasure {q(name)} =")
        mlines.append(indent(expr, 3))
        if fmt:
            mlines.append(f"\t\tformatString: {fmt}")
        mlines.append(f"\t\tdisplayFolder: {folder}")
        mlines.append(f"\t\tlineageTag: {tag()}")
        mlines.append("")
    placeholder = tmdl_column("Placeholder", "int64", True, {}, calculated=True)
    files[f"{sm}/definition/tables/_Measures.tmdl"] = tmdl_table(
        "_Measures", [placeholder], 'ROW ( "Placeholder", 0 )', kind="calculated",
        extra="\n".join(mlines) + "\n")

    rel = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        rel += [f"relationship {tag()}", f"\tfromColumn: {q(ft)}.{q(fc)}", f"\ttoColumn: {q(tt)}.{q(tc)}", ""]
    files[f"{sm}/definition/relationships.tmdl"] = "\n".join(rel)
    return files


# =============================================================================
# Report (PBIR)
# =============================================================================
def lit(v) -> dict:
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def color(hex_: str) -> dict:
    return {"solid": {"color": lit(hex_)}}


def measure(name: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": name}}


def column(table: str, name: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def proj(field: dict, display: str | None = None) -> dict:
    if "Measure" in field:
        ent, prop = "_Measures", field["Measure"]["Property"]
    else:
        ent, prop = field["Column"]["Expression"]["SourceRef"]["Entity"], field["Column"]["Property"]
    p = {"field": field, "queryRef": f"{ent}.{prop}", "nativeQueryRef": prop}
    if display:
        p["displayName"] = display
    return p


class Page:
    def __init__(self, name: str, display: str):
        self.name, self.display, self.visuals, self.no_filter = name, display, [], []

    def add(self, vname, vtype, x, y, w, h, roles=None, title=None, objects=None, sort=None, vco_extra=None):
        visual = {"visualType": vtype}
        if roles:
            visual["query"] = {"queryState": {r: {"projections": [proj(*f) if isinstance(f, tuple) else proj(f)
                                                                  for f in fs]} for r, fs in roles.items()}}
            if sort:
                visual["query"]["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}],
                                                     "isDefaultSort": False}
        if objects:
            visual["objects"] = objects
        vco = {}
        if title is not None:
            vco["title"] = [{"properties": {"show": lit(bool(title)), **({"text": lit(title)} if title else {})}}]
        if vco_extra:
            vco.update(vco_extra)
        if vco:
            visual["visualContainerObjects"] = vco
        self.visuals.append({
            "$schema": f"{SCHEMA}/visualContainer/2.2.0/schema.json",
            "name": vname,
            "position": {"x": x, "y": y, "z": len(self.visuals) * 1000, "height": h, "width": w,
                         "tabOrder": len(self.visuals) * 1000},
            "visual": visual,
        })
        return self


def textbox(page: Page, vname, x, y, w, h, text, size=20, bold=True, colour="#1F2937"):
    style = {"fontSize": f"{size}pt", "color": colour}
    if bold:
        style["fontWeight"] = "bold"
    page.add(vname, "textbox", x, y, w, h, objects={
        "general": [{"properties": {"paragraphs": [{"textRuns": [{"value": text, "textStyle": style}]}]}}]})


def card(page: Page, vname, x, y, w, h, m, label=None, font=24, colour=None):
    objs = {"labels": [{"properties": {"fontSize": lit(font), **({"color": color(colour)} if colour else {})}}],
            "categoryLabels": [{"properties": {"show": lit(label is not None)}}]}
    page.add(vname, "card", x, y, w, h, roles={"Values": [(measure(m), label)]}, objects=objs, title=False)


def default_filter(field: dict, value) -> dict:
    """Slicer default selection (stored as the slicer's own filter)."""
    ent, prop = field["Column"]["Expression"]["SourceRef"]["Entity"], field["Column"]["Property"]
    lit_v = f"{value}L" if isinstance(value, int) else "'" + str(value).replace("'", "''") + "'"
    return {"filter": {"Version": 2, "From": [{"Name": "d", "Entity": ent, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": prop}}],
                           "Values": [[{"Literal": {"Value": lit_v}}]]}}}]}}


def slicer(page: Page, vname, x, y, w, h, field, title, single=True, dropdown=True, default=None):
    objs = {"data": [{"properties": {"mode": lit("Dropdown" if dropdown else "Basic")}}],
            "selection": [{"properties": {"strictSingleSelect": lit(single), "singleSelect": lit(single)}}],
            "header": [{"properties": {"show": lit(True), "text": lit(title)}}]}
    if default is not None:
        objs["general"] = [{"properties": {"filter": default_filter(field, default)}}]
    page.add(vname, "slicer", x, y, w, h, roles={"Values": [field]}, objects=objs, title=False)


def chrome(page: Page, title: str, subtitle: str):
    textbox(page, "hdr_title", 16, 4, 860, 48, title, size=18)
    textbox(page, "hdr_sub", 16, 46, 860, 30, subtitle, size=10, bold=False, colour="#4B5563")
    card(page, "hdr_banner", 900, 12, 364, 44, "Data Banner", font=10, colour="#B45309")
    card(page, "ftr_asof", 16, 688, 560, 28, "Data As Of", font=9, colour="#6B7280")
    card(page, "ftr_credit", 700, 688, 564, 28, "Source Credit", font=9, colour="#6B7280")


def series_colours(pairs) -> list:
    return [{"selector": {"metadata": f"_Measures.{m}"}, "properties": {"fill": color(c)}} for m, c in pairs]


DEFAULTS = {"suburb": "Toowong", "quarter_label": None}


def compute_defaults(data_dir: Path) -> None:
    """Default quarter for the gap page = latest quarter with a same-quarter RTA comparison."""
    import csv
    from datetime import date
    f = data_dir / "mart_rent_gap_suburb_quarter.csv"
    if not f.exists():
        DEFAULTS["quarter_label"] = "Sep Qtr 2026"
        return
    with f.open(encoding="utf-8") as fh:
        qs = [r["quarter_end"] for r in csv.DictReader(fh) if r["rta_quarters_behind"] == "0"]
    if not qs:                       # no Domain data yet: fall back to the latest RTA quarter
        trend = data_dir / "mart_rta_suburb_trend.csv"
        if trend.exists():
            with trend.open(encoding="utf-8") as fh:
                qs = [r["quarter_end"] for r in csv.DictReader(fh)]
    if not qs:
        DEFAULTS["quarter_label"] = "Sep Qtr 2026"
        return
    d = date.fromisoformat(max(qs))
    DEFAULTS["quarter_label"] = f"{d.strftime('%b')} Qtr {d.year}"


def build_pages() -> list[Page]:
    D, S, Q = column("DimDwelling", "dwelling"), column("DimSuburb", "suburb"), column("DimQuarter", "quarter_label")

    # ---------------------------------------------------------------- page 1
    p1 = Page("p1_rising", "Where rents are rising")
    chrome(p1, "Where Queensland rents are rising",
           "Latest RTA quarter · signed rents of new tenancies · suburbs with 30+ new bonds")
    slicer(p1, "s_dwelling", 16, 76, 260, 64, D, "Dwelling")
    card(p1, "c_qld", 292, 76, 310, 80, "QLD Median Rent (latest)", "Queensland median /week")
    card(p1, "c_qld_yoy", 618, 76, 310, 80, "QLD Median YoY % (latest)", "Queensland, 1-year change")
    card(p1, "c_ranked", 944, 76, 320, 80, "Suburbs Ranked", "Suburbs with reliable data")
    p1.add("t_league", "tableEx", 16, 168, 640, 510, title="Suburb league table (sort by any column)",
           objects={"total": [{"properties": {"totals": lit(False)}}]},
           roles={"Values": [(S, "Suburb"), measure("Latest Rent"), (measure("Latest YoY %"), "1-yr change"),
                             (measure("Latest 5y %"), "5-yr change"), measure("QLD Rank"),
                             (measure("Latest New Bonds"), "New bonds")]},
           sort=(measure("Latest YoY %"), "Descending"))
    p1.add("x_momentum", "scatterChart", 672, 168, 592, 510,
           title="Momentum: 5-year vs 1-year change in signed rent",
           roles={"Category": [S], "X": [(measure("Latest 5y %"), "5-yr change")],
                  "Y": [(measure("Latest YoY %"), "1-yr change")]},
           objects={"dataPoint": [{"properties": {"fill": color(SIGNED)}}]})

    # ---------------------------------------------------------------- page 2
    p2 = Page("p2_trend", "Trend vs Queensland")
    chrome(p2, "Suburb trend vs Queensland",
           "Pick a suburb · compare year-on-year, not quarter-on-quarter (rents are seasonal)")
    slicer(p2, "s_suburb", 16, 76, 300, 64, S, "Suburb", default=DEFAULTS["suburb"])
    slicer(p2, "s_dwelling", 332, 76, 240, 64, D, "Dwelling")
    card(p2, "c_rent", 588, 76, 220, 80, "Signed Rent (latest)", "Signed rent, latest qtr")
    card(p2, "c_yoy", 820, 76, 220, 80, "Signed Rent YoY % (latest)", "1-year change")
    card(p2, "c_prem", 1052, 76, 212, 80, "Premium vs QLD % (latest)", "vs Queensland")
    p2.add("l_trend", "lineChart", 16, 168, 1248, 300, title="Signed weekly rent vs Queensland median",
           roles={"Category": [Q], "Y": [measure("Signed Rent"), measure("QLD Median Rent")]},
           objects={"dataPoint": series_colours([("Signed Rent", SIGNED), ("QLD Median Rent", NEUTRAL)])})
    p2.add("c_bonds", "clusteredColumnChart", 16, 478, 1248, 200, title="New tenancies signed (RTA new bonds)",
           roles={"Category": [Q], "Y": [measure("New Bonds")]},
           objects={"dataPoint": [{"properties": {"fill": color(SIGNED)}}]})

    # ---------------------------------------------------------------- page 3
    p3 = Page("p3_gap", "Asking vs signed")
    chrome(p3, "Are landlords asking more than tenants sign for?",
           "Domain asking rents (new listings) vs RTA signed rents · lag 0 = same quarter only")
    slicer(p3, "s_quarter", 16, 76, 220, 64, Q, "Quarter", default=DEFAULTS["quarter_label"])
    slicer(p3, "s_dwelling", 248, 76, 220, 64, D, "Dwelling")
    slicer(p3, "s_lag", 480, 76, 180, 64, column("Max RTA Lag", "Max RTA Lag"), "Max RTA lag (qtrs)", default=0)
    card(p3, "c_gap", 676, 76, 190, 80, "Gap %", "Asking above signed", colour=ASKING)
    card(p3, "c_cmp", 878, 76, 190, 80, "RTA Quarter Compared", "Compared with", font=12)
    card(p3, "c_new", 1080, 76, 184, 80, "New Listings", "New listings")
    p3.add("b_ask_vs_signed", "clusteredBarChart", 16, 168, 640, 300, title="Asking vs signed weekly rent",
           roles={"Category": [S], "Y": [measure("Asking Rent"), measure("Signed Rent (compared)")]},
           sort=(measure("Asking Rent"), "Descending"),
           objects={"dataPoint": series_colours([("Asking Rent", ASKING), ("Signed Rent (compared)", SIGNED)])})
    p3.add("b_gap", "clusteredBarChart", 672, 168, 592, 300, title="Gap % by suburb (mix-adjusted)",
           roles={"Category": [S], "Y": [measure("Gap %")]}, sort=(measure("Gap %"), "Descending"),
           objects={"dataPoint": [{"properties": {"fill": color(ASKING)}}]})
    p3.add("m_gap", "pivotTable", 16, 478, 1012, 200, title="Gap % by suburb and dwelling (blank = suppressed by RTA)",
           roles={"Rows": [(S, "Suburb")], "Columns": [(D, "Dwelling")], "Values": [measure("Gap %")]},
           objects={"subTotals": [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]})
    p3.no_filter.append(("s_dwelling", "m_gap"))   # matrix always shows every dwelling type
    card(p3, "c_low", 1040, 478, 224, 90, "Low Sample Rows", "Low-sample cells", colour="#B45309")

    # ---------------------------------------------------------------- page 4
    p4 = Page("p4_speed", "How fast places lease")
    chrome(p4, "How fast do rentals lease?",
           "Listings leaving Domain = leased or withdrawn · listings live before tracking began are excluded")
    slicer(p4, "s_dwelling", 16, 76, 260, 64, D, "Dwelling")
    card(p4, "c_closed", 292, 76, 310, 80, "Listings Closed", "Listings closed")
    card(p4, "c_dom", 618, 76, 310, 80, "Days on Market", "Median days on market")
    card(p4, "c_cut", 944, 76, 320, 80, "Price Cut %", "Cut price before leasing")
    p4.add("l_dom", "lineChart", 16, 168, 640, 250, title="Days on market by month",
           roles={"Category": [(column("Velocity", "month_start"), "Month")], "Y": [measure("Days on Market")]},
           objects={"dataPoint": series_colours([("Days on Market", ASKING)])})
    p4.add("b_dom", "clusteredBarChart", 672, 168, 592, 250, title="Days on market by suburb",
           roles={"Category": [S], "Y": [measure("Days on Market")]}, sort=(measure("Days on Market"), "Descending"),
           objects={"dataPoint": [{"properties": {"fill": color(ASKING)}}]})
    p4.add("x_gap_dom", "scatterChart", 16, 428, 640, 250,
           title="Do over-priced suburbs lease slower? (Gap % vs days on market)",
           roles={"Category": [S], "X": [measure("Gap %")], "Y": [measure("Days on Market")]},
           objects={"dataPoint": [{"properties": {"fill": color(ASKING)}}]})
    p4.add("b_cut", "clusteredBarChart", 672, 428, 592, 250, title="Share of listings that cut the price",
           roles={"Category": [S], "Y": [measure("Price Cut %")]}, sort=(measure("Price Cut %"), "Descending"),
           objects={"dataPoint": [{"properties": {"fill": color(NEUTRAL)}}]})
    return [p1, p2, p3, p4]


THEME = {
    "name": "RentTheme",
    "dataColors": [SIGNED, ASKING, NEUTRAL, "#2A9D8F", "#8E6CB4", "#C44E52", "#B8860B", "#4C9F70"],
    "background": "#FFFFFF", "foreground": "#1F2937", "tableAccent": SIGNED,
    "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": "#1F2937"},
                    "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": "#374151"}},
    "visualStyles": {"*": {"*": {"title": [{"fontColor": {"solid": {"color": "#1F2937"}}, "fontSize": 11,
                                            "fontFamily": "Segoe UI Semibold"}]}}},
}


def build_report() -> dict[str, str]:
    files: dict[str, str] = {}
    rp = f"{NAME}.Report"
    files[f"{rp}/definition.pbir"] = json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2)
    files[f"{rp}/definition/version.json"] = json.dumps({
        "$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}, indent=2)
    files[f"{rp}/definition/report.json"] = json.dumps({
        "$schema": f"{SCHEMA}/report/3.0.0/schema.json",
        "themeCollection": {"customTheme": {"name": "RentTheme.json", "reportVersionAtImport": {"visual": "2.2.0", "report": "3.0.0", "page": "2.0.0"},
                                            "type": "RegisteredResources"}},
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": "RentTheme.json", "path": "RentTheme.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True},
    }, indent=2)
    files[f"{rp}/StaticResources/RegisteredResources/RentTheme.json"] = json.dumps(THEME, indent=2)
    pages = build_pages()
    files[f"{rp}/definition/pages/pages.json"] = json.dumps({
        "$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p.name for p in pages], "activePageName": pages[0].name}, indent=2)
    for p in pages:
        files[f"{rp}/definition/pages/{p.name}/page.json"] = json.dumps({
            "$schema": f"{SCHEMA}/page/2.0.0/schema.json", "name": p.name, "displayName": p.display,
            "displayOption": "FitToPage", "height": 720, "width": 1280,
            **({"visualInteractions": [{"source": a, "target": b, "type": "NoFilter"} for a, b in p.no_filter]}
               if p.no_filter else {})}, indent=2)
        for v in p.visuals:
            files[f"{rp}/definition/pages/{p.name}/visuals/{v['name']}/visual.json"] = json.dumps(v, indent=2)
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-folder", default=DEFAULT_DATA_FOLDER)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--local-data", type=Path, default=HERE / "data", help="exported CSVs, used to pick slicer defaults")
    args = ap.parse_args()

    files = {f"{NAME}.pbip": json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True}}, indent=2)}
    compute_defaults(args.local_data)
    print("defaults:", DEFAULTS)
    files.update(build_model(args.data_folder))
    files.update(build_report())

    if args.out.exists():
        shutil.rmtree(args.out)
    for rel, content in files.items():
        p = args.out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n" if rel.endswith(".tmdl") else None)
    print(f"wrote {len(files)} files to {args.out}")


if __name__ == "__main__":
    main()
