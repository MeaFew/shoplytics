"""Recommendation prototype, cohort retention, and LTV estimation.

Three user-level analyses grouped here because they all operate on the
user-item / user-time granularity and share no dependencies on the churn or
A/B stages. Split out of scripts/pipeline.py.

- run_recommendation(): collaborative-filtering baseline with Precision@k
- run_cohort(): cohort retention heatmap + curves
- run_ltv(): LTV tier contribution pie
"""

import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import seaborn as sns
from sklearn.metrics.pairwise import cosine_similarity

from config import BEHAVIOR_WEIGHTS, IMAGES_DIR

logger = logging.getLogger("pipeline.recommendation")

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_style("whitegrid")

# Cap on high-activity users used to build the CF matrix (keeps it tractable).
TOP_USERS_LIMIT = 500


def run_recommendation(df: pl.DataFrame, k: int = 10) -> dict:
    """User-based collaborative filtering with leave-one-out evaluation."""
    top_users = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by("user_id")
        .agg(pl.len().alias("buy_count"))
        .filter(pl.col("buy_count") >= 2)
        .sort("buy_count", descending=True)
        .head(TOP_USERS_LIMIT)
    )

    buy_data = (
        df.filter(
            (pl.col("behavior_type") == "buy")
            & (pl.col("user_id").is_in(top_users["user_id"]))
        )
        .select(["user_id", "item_id"])
        .unique()
        .to_pandas()
    )

    user_list = sorted(buy_data["user_id"].unique())
    item_list = sorted(buy_data["item_id"].unique())
    user_idx = {u: i for i, u in enumerate(user_list)}
    item_idx = {it: i for i, it in enumerate(item_list)}

    matrix = np.zeros((len(user_list), len(item_list)))
    for _, row in buy_data.iterrows():
        if row["user_id"] in user_idx and row["item_id"] in item_idx:
            matrix[user_idx[row["user_id"]], item_idx[row["item_id"]]] = 1

    logger.info(
        "Matrix: %d users × %d items, sparsity: %.1f%%",
        matrix.shape[0],
        matrix.shape[1],
        (1 - matrix.sum() / matrix.size) * 100,
    )

    # Leave-one-out evaluation
    hits = 0
    total_eval = 0
    test_users = min(100, len(user_list))
    for i in range(test_users):
        u = user_list[i]
        ui = user_idx[u]
        user_items = [it for it, idx in item_idx.items() if matrix[ui, idx] == 1]
        if len(user_items) < 2:
            continue
        hidden = user_items[-1]
        train_items = user_items[:-1]
        train_vec = np.zeros(len(item_list))
        for it in train_items:
            if it in item_idx:
                train_vec[item_idx[it]] = 1

        sims = cosine_similarity([train_vec], matrix)[0]
        rec_idx = np.argsort(sims)[::-1]
        bought_set = set(train_items)
        recs = []
        for idx in rec_idx:
            it = item_list[idx]
            if it not in bought_set and it != hidden:
                recs.append(it)
            if len(recs) >= k:
                break
        total_eval += 1
        if hidden in recs:
            hits += 1

    prec = hits / total_eval if total_eval > 0 else 0
    logger.info("Precision@%d: %.4f (evaluated on %d users)", k, prec, total_eval)
    logger.info("  ✓ Recommendation system baseline done")

    return {"precision_at_k": float(prec), "k": k, "evaluated_users": total_eval}


def run_cohort(df: pl.DataFrame) -> dict:
    """Cohort retention heatmap + curves for the first 7 days."""
    first_date = df.group_by("user_id").agg(pl.col("date").min().alias("cohort_date"))
    user_dates = df.select(["user_id", "date"]).unique()

    cohort = first_date.join(user_dates, on="user_id")
    cohort = cohort.with_columns(
        ((pl.col("date") - pl.col("cohort_date")).dt.total_days()).alias("day_offset")
    )

    ret_pivot = (
        cohort.group_by(["cohort_date", "day_offset"])
        .agg(pl.col("user_id").n_unique().alias("users"))
        .sort(["cohort_date", "day_offset"])
    )

    coh_pd = ret_pivot.filter(pl.col("day_offset") <= 7).to_pandas()
    pivot_data = coh_pd.pivot(index="cohort_date", columns="day_offset", values="users")
    for d in range(1, 8):
        if d not in pivot_data.columns:
            pivot_data[d] = np.nan
    pivot_data = pivot_data.reindex(columns=range(0, 8)).fillna(0)
    for d in range(0, 8):
        pivot_data[d] = (pivot_data[d] / pivot_data[0] * 100).round(1)

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.heatmap(
        pivot_data,
        annot=True,
        fmt=".1f",
        cmap="YlGnBu",
        linewidths=0.5,
        xticklabels=[f"D{i}" for i in range(8)],
        ax=ax,
    )
    ax.set_title("Cohort Retention Heatmap (%)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Days Since First Active")
    ax.set_ylabel("Cohort Date")
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/05_cohort_heatmap.png", dpi=150)
    plt.close()
    logger.info("  ✓ 05_cohort_heatmap.png")

    # Retention curves
    fig, ax = plt.subplots(figsize=(10, 5))
    for coh_date in pivot_data.index[:5]:
        vals = pivot_data.loc[coh_date].values
        ax.plot(range(8), vals, marker="o", label=str(coh_date))
    ax.set_xlabel("Days Since First Active")
    ax.set_ylabel("Retention Rate (%)")
    ax.set_title("Cohort Retention Curves", fontsize=14, fontweight="bold")
    ax.legend(title="Cohort Date")
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/05_retention_curves.png", dpi=150)
    plt.close()
    logger.info("  ✓ 05_retention_curves.png")

    return {"charts": ["05_cohort_heatmap.png", "05_retention_curves.png"]}


def run_ltv(df: pl.DataFrame) -> dict:
    """LTV tier contribution (5-tier quantile split)."""
    lv = df.group_by("user_id").agg(
        [
            pl.col("behavior_type").filter(pl.col("behavior_type") == "pv").count().alias("pv"),
            pl.col("behavior_type").filter(pl.col("behavior_type") == "fav").count().alias("fav"),
            pl.col("behavior_type").filter(pl.col("behavior_type") == "cart").count().alias("cart"),
            pl.col("behavior_type").filter(pl.col("behavior_type") == "buy").count().alias("buy"),
        ]
    )
    lv = lv.with_columns(
        (
            pl.col("pv") * BEHAVIOR_WEIGHTS["pv"]
            + pl.col("fav") * BEHAVIOR_WEIGHTS["fav"]
            + pl.col("cart") * BEHAVIOR_WEIGHTS["cart"]
            + pl.col("buy") * BEHAVIOR_WEIGHTS["buy"]
        ).alias("value_score")
    )
    lv = lv.with_columns((pl.col("value_score") * 3).alias("ltv_estimate"))

    lv_pd = lv.filter(pl.col("ltv_estimate") > 0).sort("ltv_estimate", descending=True).to_pandas()
    lv_pd["tier"] = pd.qcut(
        lv_pd["ltv_estimate"],
        q=5,
        labels=["Bottom 20%", "20-40%", "40-60%", "60-80%", "Top 20%"],
    )
    tier_contrib = lv_pd.groupby("tier", observed=True)["ltv_estimate"].sum() / lv_pd["ltv_estimate"].sum() * 100

    fig, ax = plt.subplots(figsize=(8, 5))
    colors_lv = ["#C73E1D", "#F18F01", "#A23B72", "#2E86AB", "#00b894"]
    ax.pie(
        tier_contrib.values,
        labels=tier_contrib.index,
        autopct="%1.1f%%",
        colors=colors_lv,
        startangle=90,
        textprops={"fontsize": 10},
    )
    ax.set_title(
        "LTV contribution by user tier (Top 20% → bottom 20%)",
        fontsize=12,
        fontweight="bold",
    )
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/05_ltv_tiers.png", dpi=150)
    plt.close()
    logger.info("  Top 20%% contribution: %.1f%%", tier_contrib["Top 20%"])
    logger.info("  ✓ 05_ltv_tiers.png")

    return {
        "top_20_contribution_pct": float(tier_contrib["Top 20%"]),
        "charts": ["05_ltv_tiers.png"],
    }
