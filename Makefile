.PHONY: setup preprocess sql dbt notebook pipeline dashboard test verify clean

# ============================================================
# E-commerce User Behavior Analytics — Orchestration
# ============================================================
# In production, these steps would run on Airflow / Dagster / Prefect
# This Makefile serves as a local development entry point
# ============================================================

# Project root on sys.path so scripts can `import config` when invoked directly.
export PYTHONPATH := $(CURDIR)

# Absolute paths for dbt so DuckDB / seed references resolve the same way whether
# dbt is invoked from inside dbt/ or from the repo root with --project-dir.
export DBT_DUCKDB_PATH := $(CURDIR)/data/processed/analytics.duckdb
export DBT_DATA_PATH := $(CURDIR)/data/processed/user_behavior_cleaned.csv

setup:
	pip install -r requirements.txt

preprocess:
	python scripts/preprocess.py \
		--input data/raw/UserBehavior.csv \
		--output data/processed/

sql:
	python scripts/run_sql.py

dbt:
	cd dbt && dbt run && dbt test

notebook:
	jupyter notebook notebooks/

pipeline:
	python scripts/pipeline.py

dashboard:
	streamlit run dashboard/app.py

test:
	pytest tests/ -v

lint:
	ruff check scripts/ dashboard/ pyspark/ tests/ orchestration/
	PYTHONUTF8=1 sqlfluff lint sql/

format:
	ruff format scripts/ dashboard/ pyspark/ tests/ orchestration/

format-check:
	ruff format --check scripts/ dashboard/ pyspark/ tests/ orchestration/

audit:
	python scripts/audit_consistency.py

verify: lint format-check test audit
	python scripts/validate_data.py

# Full workflow (local equivalent of a production DAG)
all: preprocess sql dbt pipeline

clean:
	rm -f data/processed/*.duckdb
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
