#!/usr/bin/env python3
"""End-to-end analytics pipeline orchestrator.

This module used to be a 600-line monolith. It now only orchestrates the
domain stages, each of which lives in its own module:

  scripts/eda.py               — data load + EDA charts
  scripts/churn_prediction.py  — churn modeling (LR + XGBoost)
  scripts/ab_testing.py        — A/B test with hash randomization
  scripts/recommendation.py    — CF baseline + cohort + LTV

Run: ``python scripts/pipeline.py``  (entry point unchanged)

Improvements retained from the original pipeline:
1. No hardcoded paths — everything reads from config.py
2. Parquet as source (typed, fast)
3. Hash-based A/B randomization (not parity)
4. logging instead of print
5. Exception handling & input validation
6. Optional SHAP explanation for churn
7. Persisted feature engineering output
"""

import json
import logging
import warnings

from config import PROJECT_ROOT, ensure_dirs
from ab_testing import run_ab_test
from churn_prediction import run_churn_prediction
from eda import load_data, run_eda
from recommendation import run_cohort, run_ltv, run_recommendation

# Only silence specific warnings, never blanket-ignore.
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def section(title: str) -> None:
    logger.info("=" * 60)
    logger.info("  %s", title)
    logger.info("=" * 60)


def main() -> None:
    """Run the full analytics pipeline."""
    ensure_dirs()

    section("1. 加载数据 + EDA 可视化")
    df = load_data()
    eda_result = run_eda(df)

    section("2. 流失预测模型")
    churn_result = run_churn_prediction(df)

    section("3. A/B 测试分析 (改进随机化)")
    ab_result = run_ab_test(df)

    section("4. 推荐系统原型")
    rec_result = run_recommendation(df)

    section("5. Cohort 留存分析")
    cohort_result = run_cohort(df)

    section("6. LTV 价值估算")
    ltv_result = run_ltv(df)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    section("完成汇总")

    summary = {
        "generated_charts": [
            f"images/{c}" for c in (
                eda_result["charts"]
                + churn_result["charts"]
                + ab_result["charts"]
                + cohort_result["charts"]
                + ltv_result["charts"]
            )
        ],
        "key_metrics": {
            "xgb_auc": round(churn_result["xgb_auc"], 4),
            "lr_auc": round(churn_result["lr_auc"], 4),
            "ab_test_p_value": round(ab_result["p_value"], 4),
            "ab_test_significant": ab_result["significant"],
            "srm_p_value": round(ab_result["srm_pvalue"], 4),
            "usercf_precision_at_10": round(rec_result["precision_at_k"], 4),
            "top_20_ltv_contribution_pct": round(ltv_result["top_20_contribution_pct"], 1),
        },
    }

    summary_path = PROJECT_ROOT / "reports" / "pipeline_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("分析摘要已保存: %s", summary_path)

    logger.info(
        """
Key Metrics:
  XGBoost AUC:        %.4f
  Logistic Reg AUC:   %.4f
  A/B test p-value:   %.4f (%s)
  SRM p-value:        %.4f
  UserCF Precision@10: %.4f
  Top 20%% LTV contr:  %.1f%%
""",
        churn_result["xgb_auc"],
        churn_result["lr_auc"],
        ab_result["p_value"],
        "Significant" if ab_result["significant"] else "Not Significant",
        ab_result["srm_pvalue"],
        rec_result["precision_at_k"],
        ltv_result["top_20_contribution_pct"],
    )


if __name__ == "__main__":
    main()
