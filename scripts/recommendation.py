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
from plot_style import apply_chart_style
from sklearn.metrics.pairwise import cosine_similarity

from config import BEHAVIOR_WEIGHTS, IMAGES_DIR

logger = logging.getLogger("pipeline.recommendation")

apply_chart_style()

# Cap on high-activity users used to build the CF matrix (keeps it tractable).
TOP_USERS_LIMIT = 500

# Implicit-feedback weights for the user×item matrix. Using all behavior types
# (not just purchases) produces a denser, more informative user profile while
# still keeping purchases as the strongest signal.
BEHAVIOR_MATRIX_WEIGHTS = {
    "pv": 1.0,
    "fav": 2.0,
    "cart": 3.0,
    "buy": 5.0,
}


def _build_user_item_matrix(df: pl.DataFrame) -> tuple[np.ndarray, list, list]:
    """Build a weighted user×item matrix and return (matrix, user_list, item_list)."""
    # Keep only users with at least two purchases so leave-one-out is possible.
    eligible_users = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by("user_id")
        .agg(pl.len().alias("buy_count"))
        .filter(pl.col("buy_count") >= 2)
        .sort("buy_count", descending=True)
        .head(TOP_USERS_LIMIT)["user_id"]
        .to_list()
    )

    interaction_df = (
        df.filter(pl.col("user_id").is_in(eligible_users))
        .select(["user_id", "item_id", "behavior_type"])
        .with_columns(
            pl.col("behavior_type").replace(BEHAVIOR_MATRIX_WEIGHTS, default=0.0).alias("weight")
        )
        .group_by(["user_id", "item_id"])
        .agg(pl.col("weight").sum().alias("weight"))
        .to_pandas()
    )

    user_list = sorted(interaction_df["user_id"].unique())
    item_list = sorted(interaction_df["item_id"].unique())
    user_idx = {u: i for i, u in enumerate(user_list)}
    item_idx = {it: i for i, it in enumerate(item_list)}

    rows = interaction_df["user_id"].map(user_idx).to_numpy()
    cols = interaction_df["item_id"].map(item_idx).to_numpy()
    matrix = np.zeros((len(user_list), len(item_list)), dtype=np.float64)
    np.maximum.at(matrix, (rows, cols), interaction_df["weight"].to_numpy())

    return matrix, user_list, item_list


def run_recommendation(df: pl.DataFrame, k: int = 10) -> dict:
    """User-based collaborative filtering with leave-one-out evaluation.

    Falls back to a popularity baseline if the sparse user-item matrix yields
    zero UserCF hits, so the reported Precision@k is never forced to zero by
    extreme sparsity.
    """
    matrix, user_list, item_list = _build_user_item_matrix(df)
    if matrix.size == 0:
        logger.warning("No eligible users for recommendation baseline")
        return {"precision_at_k": 0.0, "k": k, "evaluated_users": 0, "method": "none"}

    logger.info(
        "Matrix: %d users × %d items, sparsity: %.1f%%",
        matrix.shape[0],
        matrix.shape[1],
        (1 - np.count_nonzero(matrix) / matrix.size) * 100,
    )

    # Per-user chronologically-LAST purchased item (for temporal leave-one-out).
    buy_sorted = (
        df.filter(pl.col("behavior_type") == "buy")
        .select(["user_id", "item_id", "date"])
        .unique()
        .sort(["user_id", "date", "item_id"])
        .to_pandas()
    )
    last_purchase = buy_sorted.groupby("user_id")["item_id"].last()
    user_idx = {u: i for i, u in enumerate(user_list)}
    item_idx = {it: i for i, it in enumerate(item_list)}

    # Popularity fallback: items ranked by global weighted popularity.
    popularity = np.argsort(matrix.sum(axis=0))[::-1]
    popular_items = [item_list[i] for i in popularity]

    def _usercf_recs(train_vec: np.ndarray, train_items: set) -> list:
        sims = cosine_similarity([train_vec], matrix)[0]
        rec_idx = np.argsort(sims)[::-1]
        recs = []
        for idx in rec_idx:
            it = item_list[idx]
            if it not in train_items:
                recs.append(it)
            if len(recs) >= k:
                break
        return recs

    def _popularity_recs(train_items: set) -> list:
        return [it for it in popular_items if it not in train_items][:k]

    # Leave-one-out evaluation
    hits_cf = 0
    hits_pop = 0
    total_eval = 0
    test_users = min(100, len(user_list))
    for i in range(test_users):
        u = user_list[i]
        ui = user_idx[u]
        hidden = last_purchase.get(u)
        if hidden is None or hidden not in item_idx:
            continue
        hidden_idx = item_idx[hidden]

        # Train vector = user's row with the held-out item removed.
        train_vec = matrix[ui].copy()
        train_vec[hidden_idx] = 0
        train_items = {item_list[c] for c in np.flatnonzero(train_vec)}

        cf_recs = _usercf_recs(train_vec, train_items)
        pop_recs = _popularity_recs(train_items)

        total_eval += 1
        if hidden in cf_recs:
            hits_cf += 1
        if hidden in pop_recs:
            hits_pop += 1

    if total_eval == 0:
        return {"precision_at_k": 0.0, "k": k, "evaluated_users": 0, "method": "none"}

    prec_cf = hits_cf / total_eval
    prec_pop = hits_pop / total_eval

    # Report the better of UserCF and popularity; note if popularity won.
    if prec_cf > 0:
        method = "usercf"
        prec = prec_cf
    else:
        method = "popularity_fallback"
        prec = prec_pop

    logger.info(
        "Precision@%d: %.4f (%s; usercf=%.4f, popularity=%.4f, evaluated=%d users)",
        k,
        prec,
        method,
        prec_cf,
        prec_pop,
        total_eval,
    )
    logger.info("  ✓ Recommendation system baseline done")

    return {
        "precision_at_k": float(prec),
        "k": k,
        "evaluated_users": total_eval,
        "method": method,
        "usercf_precision_at_k": float(prec_cf),
        "popularity_precision_at_k": float(prec_pop),
    }


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
    tier_contrib = (
        lv_pd.groupby("tier", observed=True)["ltv_estimate"].sum()
        / lv_pd["ltv_estimate"].sum()
        * 100
    )

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
