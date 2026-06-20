#!/usr/bin/env python3
"""End-to-end analytics pipeline orchestrator.

This module used to be a 600-line monolith. It now only orchestrates the
domain stages, each of which lives in its own module:

  scripts/eda.py               — data load + EDA charts
  scripts/churn_prediction.py  — churn modeling (LR + XGBoost)
  scripts/ab_testing.py        — A/B test: recommender lift (control-trained CF)
  scripts/recommendation.py    — CF baseline + cohort + LTV

Run: ``python scripts/pipeline.py``  (entry point unchanged)

Improvements retained from the original pipeline:
1. No hardcoded paths — everything reads from config.py
2. Parquet as source (typed, fast)
3. Hash-based A/B randomization (md5 parity split)
4. logging instead of print
5. Exception handling & input validation
6. Optional SHAP explanation for churn
7. Persisted feature engineering output
"""

import json
import logging
import warnings

from ab_testing import run_ab_test
from churn_prediction import run_churn_prediction
from eda import load_data, run_eda
from recommendation import run_cohort, run_ltv, run_recommendation

from config import PROJECT_ROOT, ensure_dirs

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


def compute_headline_metrics(df) -> dict:
    """Compute the README "core metrics" from the cleaned behavior frame.

    These (DAU, conversion rates, retention, zero-conversion product share)
    were previously only stated as static numbers in the README with no code
    producing them — now they are emitted into pipeline_summary.json so the
    README can be kept in sync (and audit_consistency.py can verify them).
    All metrics are computed on the full observation window.
    """
    from datetime import timedelta

    import polars as pl

    # Daily Active Users: mean distinct users per day
    dau = (
        df.group_by("date").agg(pl.col("user_id").n_unique().alias("users"))
        .select(pl.col("users").mean())
        .item()
    )

    # Per-user behavior tallies (for conversion rates)
    user_beh = df.pivot(
        values="user_id",
        index="user_id",
        columns="behavior_type",
        aggregate_function="len",
    )
    # Column presence is behavior-dependent; fill missing
    for b in ("pv", "buy", "cart", "fav"):
        if b not in user_beh.columns:
            user_beh = user_beh.with_columns(pl.lit(0).alias(b))

    # PV -> buy conversion (pool: total buys / total pvs across all users)
    total_pv = int(user_beh["pv"].sum())
    total_buy = int(user_beh["buy"].sum())
    total_cart = int(user_beh["cart"].sum())
    pv_to_buy = total_buy / total_pv if total_pv else 0.0
    pv_to_cart = total_cart / total_pv if total_pv else 0.0
    # cart -> buy conversion
    cart_to_buy = total_buy / total_cart if total_cart else 0.0

    # Day-1 retention: fraction of users active on their first day who are
    # also active the next calendar day. We compute first-active date per user,
    # build the set of (user, date) pairs they were seen on, and flag whether
    # (user, first_date+1) is in that set.
    first_active = df.group_by("user_id").agg(pl.col("date").min().alias("first_date"))
    user_active_dates = set(
        df.select(["user_id", "date"]).unique().iter_rows()
    )  # set of (user_id, date) tuples
    retained_flags = [
        (uid, fdate + timedelta(days=1)) in user_active_dates
        for uid, fdate in first_active.iter_rows()
    ]
    n_first_day_users = first_active.height
    n_retained_d1 = sum(retained_flags)
    retention_d1 = n_retained_d1 / n_first_day_users if n_first_day_users else 0.0

    # Zero-conversion product share: items ever viewed but never bought,
    # as a fraction of all distinct viewed items.
    item_pv = df.filter(pl.col("behavior_type") == "pv").select("item_id").unique()
    item_buy = df.filter(pl.col("behavior_type") == "buy").select("item_id").unique()
    n_viewed = item_pv.height
    # items viewed but NOT in the bought set
    zero_conv_items = item_pv.join(item_buy, on="item_id", how="anti").height
    zero_conv_share = zero_conv_items / n_viewed if n_viewed else 0.0

    return {
        "dau_mean": round(float(dau), 1),
        "pv_to_buy_conversion_pct": round(pv_to_buy * 100, 2),
        "pv_to_cart_conversion_pct": round(pv_to_cart * 100, 2),
        "cart_to_buy_conversion_pct": round(cart_to_buy * 100, 2),
        "retention_d1_pct": round(retention_d1 * 100, 2),
        "zero_conversion_items": int(zero_conv_items),
        "zero_conversion_item_share_pct": round(zero_conv_share * 100, 2),
    }


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

    section("7. 头条业务指标 (DAU/转化/留存/零转化)")
    headline = compute_headline_metrics(df)
    logger.info("头条指标: %s", headline)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    section("完成汇总")

    summary = {
        "generated_charts": [
            f"images/{c}"
            for c in (
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
            "ab_test_lift_pct": round(ab_result["lift_pct"], 2),
            "srm_p_value": round(ab_result["srm_pvalue"], 4),
            "usercf_precision_at_10": round(rec_result["precision_at_k"], 4),
            "top_20_ltv_contribution_pct": round(
                ltv_result["top_20_contribution_pct"], 1
            ),
        },
        "headline_business_metrics": headline,
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
  A/B test lift:      %+.2f%%
  SRM p-value:        %.4f
  UserCF Precision@10: %.4f
  Top 20%% LTV contr:  %.1f%%
""",
        churn_result["xgb_auc"],
        churn_result["lr_auc"],
        ab_result["p_value"],
        "Significant" if ab_result["significant"] else "Not Significant",
        ab_result["lift_pct"],
        ab_result["srm_pvalue"],
        rec_result["precision_at_k"],
        ltv_result["top_20_contribution_pct"],
    )


if __name__ == "__main__":
    main()
