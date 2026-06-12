.PHONY: setup preprocess sql dbt notebook pipeline dashboard test verify clean

# ============================================================
# E-commerce User Behavior Analytics — Orchestration
# ============================================================
# In production, these steps would run on Airflow / Dagster / Prefect
# This Makefile serves as a local development entry point
# ============================================================

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
	ruff check scripts/ dashboard/ pyspark/ tests/ orchestration/ --ignore E501,E402
	sqlfluff lint sql/

verify: lint format-check test audit
	python scripts/validate_data.py

# Full workflow (local equivalent of a production DAG)
all: preprocess sql dbt pipeline

clean:
	rm -f data/processed/*.duckdb
	find . -type d -name "__pycache__" -exec rm -rf {} +

# === Quality gates (extended) ===

format:
	ruff format scripts/ dashboard/ pyspark/

format-check:
	ruff format --check scripts/ dashboard/ pyspark/

audit:
	python scripts/audit_consistency.py
