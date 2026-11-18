# One-command entry points. Everything runs in Docker; only Docker is needed on the host.
# Without make (e.g. Windows PowerShell), run the command shown after each target by hand.

COMPOSE ?= docker compose
RUN      = $(COMPOSE) run --rm app

.DEFAULT_GOAL := help
.PHONY: help build up demo real test wap-check dbt-test docs pbip psql logs down clean

help:  ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-10s %s\n", $$1, $$2}'

build:  ## build the pipeline image
	$(COMPOSE) build app

up:  ## start Postgres (localhost:5433, user/password/db: rent)
	$(COMPOSE) up -d --wait db

demo: up  ## full pipeline on synthetic data: schemas, RTA, Domain, dbt build, export
	$(RUN) bash scripts/pipeline.sh demo

real: up  ## full pipeline on the real RTA workbook in data/raw/rta/ (+ Domain if keys are set)
	$(RUN) bash scripts/pipeline.sh real

test: up  ## pytest, with the database tests run against a separate rent_test database
	$(COMPOSE) run --rm -e TEST_DATABASE_URL=postgresql://rent:rent@db:5432/rent_test app pytest -q

wap-check: up  ## prove write-audit-publish: a corrupted load fails and the published marts stay unchanged (after demo)
	$(RUN) bash scripts/check_wap.sh

dbt-test: up  ## dbt tests only (after demo or real)
	$(RUN) bash -c "cd dbt && dbt test --profiles-dir ."

docs: up  ## dbt docs and lineage graph on http://localhost:8080
	$(COMPOSE) run --rm -p 8080:8080 app bash -c "cd dbt && dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir . --host 0.0.0.0 --port 8080 --no-browser"

pbip:  ## regenerate the Power BI project from powerbi/build_pbip.py
	$(RUN) python powerbi/build_pbip.py

psql: up  ## open psql in the database
	$(COMPOSE) exec db psql -U rent -d rent

logs:  ## Postgres logs
	$(COMPOSE) logs -f db

down:  ## stop containers (data is kept)
	$(COMPOSE) down

clean:  ## stop containers and delete the database volume
	$(COMPOSE) down -v
