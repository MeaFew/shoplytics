"""
Prefect flow: E-commerce Analytics Pipeline

Runs locally with `python orchestration/pipeline_flow.py`.
In production, deploy to Prefect Cloud or a self-hosted server.

Install: pip install prefect
"""

from datetime import datetime
from pathlib import Path

# --- Prefect imports (install: pip install prefect) ---
try:
    from prefect import flow, task
    HAS_PREFECT = True
except ImportError:
    HAS_PREFECT = False
    # Define no-op decorators so the file is still importable
    def flow(*args, **kwargs):
        def wrapper(fn):
            return fn
        return wrapper
    def task(*args, **kwargs):
        def wrapper(fn):
            return fn
        return wrapper


@task(name="preprocess-data", retries=1, tags=["etl"])
def preprocess_data(input_path: str = "data/raw/UserBehavior.csv",
                    output_dir: str = "data/processed/"):
    """Step 1: Clean and preprocess raw user behavior data."""
    import subprocess
    result = subprocess.run([
        "python", "scripts/preprocess.py",
        "--input", input_path,
        "--output", output_dir,
    ], capture_output=True, text=True)
    print(result.stdout[-500:])
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return f"Preprocessed → {output_dir}"


@task(name="run-sql-analysis", retries=1, tags=["sql"])
def run_sql_analysis(db_path: str = "data/processed/analytics.duckdb"):
    """Step 2: Execute SQL analysis scripts on the preprocessed data."""
    import duckdb
    con = duckdb.connect(db_path)
    sql_dir = Path("sql")
    scripts = sorted(sql_dir.glob("0*.sql"))
    for script in scripts:
        print(f"  Running {script.name}...")
        sql = script.read_text(encoding="utf-8")
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            lines = [ln for ln in stmt.splitlines() if ln.strip() and not ln.strip().startswith("--")]
            if not lines:
                continue
            con.execute(stmt)
    con.close()
    return f"SQL analysis complete — {len(scripts)} scripts executed"


@task(name="run-dbt-models", retries=1, tags=["dbt"])
def run_dbt_models():
    """Step 3: Run dbt models and tests."""
    import subprocess
    result = subprocess.run(["dbt", "run"], cwd="dbt", capture_output=True, text=True)
    print(result.stdout[-500:])
    result = subprocess.run(["dbt", "test"], cwd="dbt", capture_output=True, text=True)
    print(result.stdout[-500:])
    return "dbt models and tests completed"


@task(name="run-modeling-pipeline", retries=1, tags=["modeling"])
def run_modeling_pipeline():
    """Step 4: Run Python analysis pipeline (EDA, churn, A/B, cohort, LTV)."""
    import subprocess
    result = subprocess.run(
        ["python", "scripts/pipeline.py"],
        capture_output=True, text=True
    )
    print(result.stdout[-800:])
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-500:])
    return "Modeling pipeline complete — charts generated in images/"


@flow(name="ecommerce-analytics-pipeline",
      description="Daily ETL + analytics pipeline for user behavior data",
      log_prints=True)
def analytics_pipeline():
    """
    Production-equivalent pipeline.

    Schedule: daily at 08:00 UTC (T+1 after data lands).
    Run locally: python orchestration/pipeline_flow.py
    """
    print(f"Pipeline started at {datetime.now().isoformat()}")

    result_1 = preprocess_data()
    result_2 = run_sql_analysis()
    result_3 = run_dbt_models()
    result_4 = run_modeling_pipeline()

    print("Pipeline finished successfully.")
    return [result_1, result_2, result_3, result_4]


if __name__ == "__main__":
    if HAS_PREFECT:
        print("Running with Prefect orchestration...")
        analytics_pipeline()
    else:
        print("Prefect not installed. Running tasks sequentially...")
        print(preprocess_data.fn())
        print(run_sql_analysis.fn())
        print(run_modeling_pipeline.fn())
        print("Done — install Prefect (pip install prefect) for full orchestration.")
