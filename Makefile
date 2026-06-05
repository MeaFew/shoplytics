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

verify:
	ruff check scripts/ dashboard/ pyspark/ tests/ --ignore E501,F401,E402
	sqlfluff lint sql/
	pytest tests/ -v
	python scripts/validate_data.py

# Full workflow (local equivalent of a production DAG)
all: preprocess sql dbt pipeline

clean:
	rm -rf data/processed/*.duckdb
	find . -type d -name "__pycache__" -exec rm -rf {} +
