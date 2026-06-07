"""Windows-compatible one-shot pipeline runner.

Replaces `make all` on systems without GNU Make (e.g., Windows).
Usage: python run_all.py
"""

import os
import subprocess
import sys
from pathlib import Path


def run(cmd: str, cwd: Path | None = None):
    print(f"\n{'=' * 60}")
    print(f">>> {cmd}")
    print("=" * 60)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd) if cwd else "."
    result = subprocess.run(cmd, shell=True, cwd=cwd, env=env)
    if result.returncode != 0:
        print(f"WARNING: Command failed with exit code {result.returncode}")
        return False
    return True


def main():
    here = Path(__file__).resolve().parent

    # Note: sql and dbt steps require DuckDB and dbt to be installed/configured.
    # This runner focuses on the core Python pipeline.
    steps = [
        ("Preprocessing", "python scripts/preprocess.py --input data/raw/UserBehavior.csv --output data/processed/"),
        ("Analysis Pipeline", "python scripts/pipeline.py"),
    ]

    print("E-commerce User Behavior Analytics — Core Pipeline")
    print("=" * 60)
    print("Note: SQL analysis and dbt models require DuckDB/dbt setup.")
    print("      Run 'make sql' and 'make dbt' separately if configured.")
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
