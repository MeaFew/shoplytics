"""A/B test analysis with hash-based randomization and SRM check.

Splits out of scripts/pipeline.py. Returns conversion rates, Z-test p-value,
and SRM (Sample Ratio Mismatch) p-value for the pipeline summary.
"""

import hashlib
import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns
from scipy import stats

from config import IMAGES_DIR

logger = logging.getLogger("pipeline.abtest")

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_style("whitegrid")


def hash_group(user_id: int, salt: str = "ab_test_v1") -> str:
    """Hash-based random assignment — more random than odd/even parity."""
    h = hashlib.md5(f"{user_id}_{salt}".encode()).hexdigest()
    return "control" if int(h, 16) % 2 == 0 else "treatment"


def run_ab_test(df: pl.DataFrame, split_date: str = "2017-12-01") -> dict:
    """Run A/B test on post-split-date users. Returns metrics + chart filename."""
    df_sample = df.filter(pl.col("date") >= pl.date(*map(int, split_date.split("-"))))
    user_conv = df_sample.group_by("user_id").agg(
        [
            pl.col("behavior_type").filter(pl.col("behavior_type") == "pv").count().alias("pv"),
            pl.col("behavior_type").filter(pl.col("behavior_type") == "buy").count().alias("buy"),
        ]
    ).with_columns(
        [
            pl.col("user_id").map_elements(hash_group, return_dtype=pl.Utf8).alias("group"),
            (pl.col("buy") > 0).cast(pl.Int64).alias("converted"),
        ]
    )

    control = user_conv.filter(pl.col("group") == "control")
    treatment = user_conv.filter(pl.col("group") == "treatment")

    c_rate = control["converted"].mean()
    t_rate = treatment["converted"].mean()
    logger.info("Control:   %s users, conv=%.2f%%", f"{control.height:,}", c_rate * 100)
    logger.info("Treatment: %s users, conv=%.2f%%", f"{treatment.height:,}", t_rate * 100)

    # SRM check
    total = control.height + treatment.height
    expected_ratio = 0.5
    srm_chi2 = (
        ((control.height - total * expected_ratio) ** 2) / (total * expected_ratio)
        + ((treatment.height - total * expected_ratio) ** 2) / (total * expected_ratio)
    )
    srm_pvalue = 1 - stats.chi2.cdf(srm_chi2, df=1)
    logger.info(
        "SRM check: χ²=%.4f, p=%.4f (p<0.05 表示分组不均衡)", srm_chi2, srm_pvalue
    )

    # Two-proportion Z-test
    n_c, n_t = control.height, treatment.height
    x_c, x_t = control["converted"].sum(), treatment["converted"].sum()
    p_pool = (x_c + x_t) / (n_c + n_t)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    z = (t_rate - c_rate) / se if se > 0 else 0
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    diff = t_rate - c_rate
    ci = 1.96 * se
    logger.info("Z-statistic: %.4f, p-value: %.4f", z, p_value)
    logger.info("95%% CI: [%.4f, %.4f]", diff - ci, diff + ci)
    logger.info(
        "Conclusion: %s (α=0.05)",
        "Significant" if p_value < 0.05 else "Not Significant",
    )

    significant = bool(p_value < 0.05)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.bar(["Control", "Treatment"], [c_rate * 100, t_rate * 100], color=["#2E86AB", "#F18F01"])
    ax.set_ylabel("Conversion Rate (%)")
    ax.set_title(
        f"A/B Test: p={p_value:.4f}, {'Significant' if significant else 'Not Significant'}",
        fontsize=13,
        fontweight="bold",
    )
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/03_ab_test.png", dpi=150)
    plt.close()
    logger.info("  ✓ 03_ab_test.png")

    return {
        "p_value": float(p_value),
        "significant": significant,
        "srm_pvalue": float(srm_pvalue),
        "control_rate": float(c_rate),
        "treatment_rate": float(t_rate),
        "charts": ["03_ab_test.png"],
    }
