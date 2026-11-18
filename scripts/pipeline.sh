#!/usr/bin/env bash
# Run the whole pipeline against whatever database the environment points at.
#   demo : synthetic RTA workbook + synthetic Domain listings (no downloads, no keys)
#   real : the RTA workbook in data/raw/rta/ (or RTA_FILE), plus Domain if keys are set
set -euo pipefail
MODE="${1:-demo}"
cd "$(dirname "$0")/.."

[ -f dbt/profiles.yml ] || cp dbt/profiles.yml.example dbt/profiles.yml

echo "==> schemas"
python scripts/init_db.py

case "$MODE" in
  demo)
    FIXTURE=data/raw/rta/demo-rta-bond-statistics.xlsx
    echo "==> RTA (synthetic workbook through the real parser)"
    # build once: a rebuilt workbook gets a new hash and would defeat --if-changed
    [ -f "$FIXTURE" ] || python scripts/make_rta_fixture.py "$FIXTURE"
    python ingest_rta.py --file "$FIXTURE" --geo suburb,state --if-changed
    echo "==> Domain (synthetic listings)"
    python scripts/generate_fake_domain.py --truncate
    ;;
  real)
    RTA_FILE="${RTA_FILE:-data/raw/rta/rta-bond-statistics.xlsx}"
    if [ ! -f "$RTA_FILE" ]; then
      echo "RTA workbook not found at $RTA_FILE" >&2
      echo "Download it from the RTA rental bond data page and save it there." >&2
      exit 1
    fi
    echo "==> RTA ($RTA_FILE)"
    python ingest_rta.py --file "$RTA_FILE" --geo suburb,state --if-changed
    # keys may live in the environment or in .env; envconfig reads both
    if python -c "import os, sys; from envconfig import load_env; load_env(); sys.exit(0 if os.getenv('DOMAIN_CLIENT_ID') and os.getenv('DOMAIN_CLIENT_SECRET') and 'your_' not in os.getenv('DOMAIN_CLIENT_ID') else 1)"; then
      echo "==> Domain (live API)"
      python ingest_domain.py
    else
      echo "==> Domain skipped (no DOMAIN_CLIENT_ID / DOMAIN_CLIENT_SECRET)"
    fi
    ;;
  *)
    echo "usage: $0 [demo|real]" >&2
    exit 2
    ;;
esac

echo "==> dbt build"
(cd dbt && dbt build --profiles-dir . --fail-fast)

echo "==> export marts for Power BI"
python scripts/export_marts.py
echo "Done. CSVs are in powerbi/data/"
