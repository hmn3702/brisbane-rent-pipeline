#!/usr/bin/env bash
# Write-audit-publish: build and test every dbt layer in *__audit schemas, then swap them in
# only if everything passed. On failure the published schemas are untouched and the *__audit
# schemas are left behind for inspection (the next run drops them first).
set -euo pipefail
cd "$(dirname "$0")/../dbt"
[ -f profiles.yml ] || cp profiles.yml.example profiles.yml

dbt run-operation wap_prepare --profiles-dir .
if dbt build --profiles-dir . --vars '{wap_suffix: __audit}' "$@"; then
    dbt run-operation wap_publish --profiles-dir .
    echo "WAP: published"
else
    echo "WAP: audit failed - published tables left unchanged; inspect the *__audit schemas" >&2
    exit 1
fi
