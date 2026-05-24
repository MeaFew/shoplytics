.PHONY: setup preprocess sql dbt notebook pipeline dashboard test clean

# ============================================================
# E-commerce User Behavior Analytics — Orchestration
# ============================================================
# In production, these steps would run on Airflow / Dagster / Prefect
# This Makefile serves as a local development entry point
# ============================================================

setup:
	pip install -r requirements.txt

preprocess:
	python python/scripts/01_data_preprocessing_polars.py \
		--input data/raw/UserBehavior.csv \
		--output data/processed/

sql:
	sqlite3 data/processed/analytics.db < sql/01_database_setup.sql
	sqlite3 data/processed/analytics.db < sql/02_user_retention.sql
	sqlite3 data/processed/analytics.db < sql/03_conversion_funnel.sql
	sqlite3 data/processed/analytics.db < sql/04_rfm_model.sql
	sqlite3 data/processed/analytics.db < sql/05_ab_test_framework.sql
	sqlite3 data/processed/analytics.db < sql/06_anomaly_detection.sql
	sqlite3 data/processed/analytics.db < sql/07_product_analysis.sql

dbt:
	cd dbt && dbt run && dbt test

notebook:
	jupyter notebook python/notebooks/

pipeline:
	python python/scripts/run_analysis_pipeline.py

dashboard:
	cd dashboard && streamlit run app.py

test:
	pytest tests/ -v

# Full workflow (local equivalent of a production DAG)
all: preprocess sql dbt pipeline

clean:
	rm -rf data/processed/*.db
	find . -type d -name "__pycache__" -exec rm -rf {} +
