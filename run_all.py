"""Windows-compatible one-shot pipeline runner.

Replaces `make all` on systems without GNU Make (e.g., Windows).
Usage: python run_all.py
"""

import os
import subprocess
import sys
from pathlib import Path

# Force UTF-8 mode for child processes on Windows before any heavy imports.
os.environ.setdefault("PYTHONUTF8", "1")


def run(cmd: list[str], cwd: Path | None = None):
    print(f"\n{'=' * 60}")
    print(f">>> {' '.join(cmd)}")
    print("=" * 60)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd) if cwd else "."
    # cmd is a list; no shell=True — avoids shell-injection surface and
    # correctly handles paths with spaces. (Previously shell=True with a
    # string built command.)
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        print(f"WARNING: Command failed with exit code {result.returncode}")
        return False
    return True


def main():
    here = Path(__file__).resolve().parent

    # Note: the pipeline covers all four steps:
    # preprocessing (Python), SQL analysis (DuckDB), dbt models/tests, and
    # analysis pipeline (Python). Each step is an argv list (no shell=True).
    steps = [
        (
            "Preprocessing",
            [
                "python",
                "scripts/preprocess.py",
                "--input",
                "data/raw/UserBehavior.csv",
                "--output",
                "data/processed/",
            ],
        ),
        ("SQL Analysis", ["python", "scripts/run_sql.py"]),
        # Run dbt from the project root so relative paths resolve. dbt run and
        # dbt test are separate steps (no `&&` shell chaining needed).
        (
            "dbt Models",
            ["dbt", "run", "--project-dir", "dbt", "--profiles-dir", "dbt"],
        ),
        (
            "dbt Tests",
            ["dbt", "test", "--project-dir", "dbt", "--profiles-dir", "dbt"],
        ),
        ("Analysis Pipeline", ["python", "scripts/pipeline.py"]),
    ]

    print("E-commerce User Behavior Analytics - Full Pipeline")
    print("=" * 60)
    print("Note: SQL/dbt steps require DuckDB and dbt installed. Install with:")
    print("      pip install duckdb dbt-duckdb")
    print("=" * 60)

    for name, cmd in steps:
        if not run(cmd, cwd=here):
            print(f"\nPipeline stopped at step: {name}")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("Core pipeline completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
