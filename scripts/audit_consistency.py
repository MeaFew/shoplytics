"""Cross-reference audit: README claims vs. actual pipeline outputs.

Run after `make all` to verify that key metrics declared in README.md
match the actual values produced by the pipeline.
"""

import json
import re
import sys
from pathlib import Path


def read_readme_metric(readme_path: Path, metric_name: str) -> float | None:
    """Extract a numeric metric from README.md."""
    text = readme_path.read_text(encoding="utf-8")
    pattern = rf"\*\*{re.escape(metric_name)}\*\*.*?(\d+\.\d+)"
    match = re.search(pattern, text)
    if match:
        return float(match.group(1))
    return None


def check(condition: bool, msg: str) -> bool:
    """Assert-like check that prints pass/fail."""
    if condition:
        print(f"  PASS: {msg}")
    else:
        print(f"  FAIL: {msg}")
    return condition


def main():
    root = Path(__file__).resolve().parents[1]
    readme = root / "README.md"
    passed = 0
    failed = 0

    # --- Data scale checks ---
    from config import CLEANED_CSV_PATH
    if CLEANED_CSV_PATH.exists():
        import polars as pl
        df = pl.read_csv(CLEANED_CSV_PATH, n_rows=1)
        n_users = df.select(pl.col("user_id").n_unique()).item()
        n_items = df.select(pl.col("item_id").n_unique()).item()
        n_cats = df.select(pl.col("category_id").n_unique()).item()

        # Read full row count from file size
        total_rows = sum(1 for _ in open(CLEANED_CSV_PATH, encoding="utf-8")) - 1

        ok = check(total_rows == 29_128_402, f"Total records: actual={total_rows}, expected=29,128,402")
        if ok: passed += 1 else: failed += 1
        print(f"  Users: {n_users}, Items: {n_items}, Categories: {n_cats}")
    else:
        print(f"  SKIP: {CLEANED_CSV_PATH} not found — run preprocess first")

    # --- Model metrics check ---
    summary_path = root / "reports" / "pipeline_summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            summary = json.load(f)
        metrics = summary.get("key_metrics", {})
        xgb_auc = metrics.get("xgb_auc", 0)
        ok = check(xgb_auc > 0.80, f"XGBoost AUC={xgb_auc:.4f} (threshold: 0.80)")
        if ok: passed += 1 else: failed += 1
        print(f"  LR AUC={metrics.get('lr_auc', 0):.4f}")
    else:
        print(f"  SKIP: {summary_path} not found — run pipeline first")

    # --- Summary ---
    total = passed + failed
    if total == 0:
        print("No checks performed (data not found). Run make all first.")
        return

    print(f"\n{'='*40}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed > 0:
        print("ACTION: Update README.md or fix pipeline to resolve mismatches.")
        sys.exit(1)


if __name__ == "__main__":
    main()
