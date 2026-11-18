#!/usr/bin/env bash
# Proves write-audit-publish works: corrupt one raw value, check the run fails and the published
# marts are byte-for-byte unchanged, then restore and check a clean run publishes again.
# Needs a database that has already been through scripts/pipeline.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
q() { python -c "import sys, psycopg; from envconfig import load_env, database_url; load_env(); print(psycopg.connect(database_url(), autocommit=True).execute(sys.argv[1]).fetchone()[0])" "$1"; }

CHECKSUM="select md5(string_agg(t::text, '|' order by t::text)) from marts.mart_rta_suburb_latest t"
LATEST="(select max(quarter_end) from raw.rta_bond_stats)"
CELL="geo_level = 'state' and dwelling = 'All dwellings' and measure = 'median_rent' and quarter_end = $LATEST"

before=$(q "$CHECKSUM")
q "update raw.rta_bond_stats set value = value * 10 where $CELL returning 1" >/dev/null
echo "corrupted: Queensland median rent x10 in the latest quarter"

if bash scripts/dbt_wap.sh >/tmp/wap_fail.log 2>&1; then
    q "update raw.rta_bond_stats set value = value / 10 where $CELL returning 1" >/dev/null
    echo "FAIL: the corrupted build was published" >&2; exit 1
fi
sed 's/\x1b\[[0-9;]*m//g' /tmp/wap_fail.log | grep -oE "FAIL [0-9]+ [A-Za-z][A-Za-z0-9_]{2,}" | sed 's/^FAIL [0-9]* /  test failed: /' || true

after=$(q "$CHECKSUM")
[ "$before" = "$after" ] || { echo "FAIL: published marts changed" >&2; exit 1; }
[ "$(q "select count(*) from pg_namespace where nspname = 'marts__audit'")" = "1" ] || { echo "FAIL: no audit schema left to inspect" >&2; exit 1; }
echo "ok: build rejected, published marts unchanged, marts__audit kept for inspection"

q "update raw.rta_bond_stats set value = value / 10 where $CELL returning 1" >/dev/null
bash scripts/dbt_wap.sh >/tmp/wap_ok.log 2>&1 || { cat /tmp/wap_ok.log; echo "FAIL: clean rebuild did not publish" >&2; exit 1; }
[ "$(q "$CHECKSUM")" = "$before" ] || { echo "FAIL: clean rebuild differs from the original" >&2; exit 1; }
[ "$(q "select count(*) from pg_namespace where nspname like '%\_\_audit' or nspname like '%\_\_old'")" = "0" ] || { echo "FAIL: leftover schemas" >&2; exit 1; }
echo "ok: restored data published, no leftover schemas"
