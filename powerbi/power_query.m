// =============================================================================
// Power Query (M) for the Brisbane Rent dashboard
// -----------------------------------------------------------------------------
// How to use: Power BI Desktop > Home > Transform data > New Source > Blank Query,
// then Advanced Editor and paste ONE section per query. Name each query exactly as
// the header says (DataFolder, Gap, RtaLatest, RtaTrend, Velocity, Manifest,
// DimSuburb, DimDwelling, DimQuarter).
//
// Option A (default): read the CSVs from scripts/export_marts.py.
// Option B: read straight from Postgres - see the bottom of this file.
//
// All type conversions pass culture "en-US" so "8.5" stays 8.5 on Windows set to
// Vietnamese / European number formats (decimal comma).
// =============================================================================


// ---------------------------------------------------------------- DataFolder
// Parameter (Manage Parameters > New): type Text. Change to your own path.
"E:\project\QLD-rent-analysis\rent-pipeline\powerbi\data" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]


// ---------------------------------------------------------------- Gap
let
    Source  = Csv.Document(File.Contents(DataFolder & "\mart_rent_gap_suburb_quarter.csv"),
                [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"suburb", type text}, {"rta_suburb", type text}, {"quarter_end", type date},
        {"dwelling", type text}, {"n_new_listings", Int64.Type}, {"median_asking_rent", type number},
        {"rta_quarter_end", type date}, {"rta_quarters_behind", Int64.Type},
        {"median_signed_rent", type number}, {"rta_new_bonds", type number},
        {"gap_dollars", type number}, {"gap_pct", type number}, {"is_low_sample", type logical},
        {"gap_pct_mix_adjusted", type number}}, "en-US")
in
    Typed


// ---------------------------------------------------------------- RtaLatest
let
    Source  = Csv.Document(File.Contents(DataFolder & "\mart_rta_suburb_latest.csv"),
                [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"area_name", type text}, {"suburb", type text}, {"area_postcode", type text},
        {"location_label", type text}, {"dwelling", type text}, {"quarter_end", type date},
        {"median_weekly_rent", type number}, {"median_weekly_rent_prev_year", type number},
        {"rent_yoy_pct", type number}, {"median_weekly_rent_5y_ago", type number},
        {"rent_5y_pct", type number}, {"new_bonds", type number}, {"bonds_held", type number},
        {"rent_rank_qld", Int64.Type}, {"n_suburbs_ranked", Int64.Type}, {"is_tracked", type logical}}, "en-US")
in
    Typed


// ---------------------------------------------------------------- RtaTrend
let
    Source  = Csv.Document(File.Contents(DataFolder & "\mart_rta_suburb_trend.csv"),
                [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"area_name", type text}, {"suburb", type text}, {"area_postcode", type text},
        {"location_label", type text}, {"dwelling", type text}, {"dwelling_type", type text},
        {"bedrooms", Int64.Type}, {"quarter_end", type date}, {"median_weekly_rent", type number},
        {"rent_yoy_pct", type number}, {"new_bonds", type number}, {"bonds_held", type number},
        {"qld_median_weekly_rent", type number}, {"premium_vs_qld_pct", type number},
        {"is_tracked", type logical}}, "en-US")
in
    Typed


// ---------------------------------------------------------------- Velocity
let
    Source  = Csv.Document(File.Contents(DataFolder & "\mart_listing_velocity_suburb_month.csv"),
                [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed   = Table.TransformColumnTypes(Headers, {
        {"suburb", type text}, {"rta_suburb", type text}, {"month_start", type date},
        {"quarter_end", type date}, {"dwelling", type text}, {"n_listings_closed", Int64.Type},
        {"median_days_on_market", type number}, {"pct_with_price_cut", type number},
        {"median_final_asking_rent", type number}}, "en-US")
in
    Typed


// ---------------------------------------------------------------- Manifest
// One row: drives the DEMO DATA banner and the "data as of" label.
let
    Json  = Json.Document(File.Contents(DataFolder & "\manifest.json")),
    Row   = #table(
              type table [exported_at = text, domain_data_is_synthetic = logical,
                          domain_synthetic_share = number, rta_latest_quarter = date],
              {{ Json[exported_at], Json[domain_data_is_synthetic],
                 Json[domain_synthetic_share], Date.FromText(Json[rta_latest_quarter], "en-US") }})
in
    Row


// ---------------------------------------------------------------- DimSuburb
// Built in Power Query (not DAX) to avoid circular-dependency errors with calculated tables.
let
    Cols   = Table.SelectColumns(RtaTrend, {"area_name", "suburb", "area_postcode", "location_label", "is_tracked"}),
    Unique = Table.Distinct(Cols, {"area_name"})
in
    Unique


// ---------------------------------------------------------------- DimDwelling
let
    All     = List.Distinct(RtaTrend[dwelling] & Gap[dwelling] & Velocity[dwelling]),
    Base    = Table.FromList(All, Splitter.SplitByNothing(), type table [dwelling = text]),
    Order   = {"All dwellings", "Flat 1", "Flat 2", "Flat 3", "House 2", "House 3", "House 4",
               "Townhouse 2", "Townhouse 3", "Other"},
    Sorted  = Table.AddColumn(Base, "dwelling_sort",
                each let i = List.PositionOf(Order, [dwelling]) in if i < 0 then 99 else i, Int64.Type),
    Typed   = Table.AddColumn(Sorted, "dwelling_type",
                each Text.BeforeDelimiter([dwelling], " "), type text)
in
    Typed


// ---------------------------------------------------------------- DimQuarter
let
    All     = List.Distinct(RtaTrend[quarter_end] & Gap[quarter_end] & Velocity[quarter_end]),
    Base    = Table.FromList(All, Splitter.SplitByNothing(), type table [quarter_end = date]),
    Year    = Table.AddColumn(Base, "year", each Date.Year([quarter_end]), Int64.Type),
    Label   = Table.AddColumn(Year, "quarter_label",
                each Date.ToText([quarter_end], [Format = "MMM", Culture = "en-AU"]) & " Qtr "
                     & Text.From(Date.Year([quarter_end])), type text),
    Index   = Table.AddColumn(Label, "quarter_index",
                each Date.Year([quarter_end]) * 4 + Date.QuarterOfYear([quarter_end]), Int64.Type)
in
    Index


// =============================================================================
// Option B: Postgres instead of CSV (Power BI Desktop has a built-in PostgreSQL
// connector). Replace the first three steps of Gap / RtaLatest / RtaTrend / Velocity
// with the two lines below (booleans and types come through natively, so the
// TransformColumnTypes step can be dropped):
//
//     Source = PostgreSQL.Database("localhost:5432", "rent"),
//     Typed  = Source{[Schema = "marts", Item = "mart_rent_gap_suburb_quarter"]}[Data]
//
// and for Manifest:
//
//     Source = PostgreSQL.Database("localhost:5432", "rent", [Query =
//       "select now()::text as exported_at,
//               bool_and(coalesce((payload->>'_synthetic')::boolean, false)) as domain_data_is_synthetic,
//               avg(case when (payload->>'_synthetic')::boolean then 1 else 0 end) as domain_synthetic_share,
//               (select max(quarter_end) from raw.rta_bond_stats) as rta_latest_quarter
//        from raw.domain_rent_listings"])
// =============================================================================
