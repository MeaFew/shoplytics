"""Exploratory data analysis & visualization.

Loads the cleaned parquet, produces EDA charts, and returns the loaded
DataFrame plus a small set of dataset-level stats for downstream stages.

Split out of scripts/pipeline.py so each analysis domain is independently
testable and runnable.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl
import seaborn as sns

from config import CLEANED_PARQUET_PATH, IMAGES_DIR

logger = logging.getLogger("pipeline.eda")

# Shared chart styling (matches the original pipeline's look).
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_style("whitegrid")


def load_data(path: Path = CLEANED_PARQUET_PATH) -> pl.DataFrame:
    """Load cleaned parquet and parse the date column if it is still a string."""
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}. 请先运行预处理脚本。")

    t0 = datetime.now()
    df = pl.read_parquet(path)
    elapsed = (datetime.now() - t0).total_seconds()
    logger.info(
        "Rows: %s | Columns: %s | Time: %.1fs",
        f"{df.height:,}",
        len(df.columns),
        elapsed,
    )

    if df.schema.get("date") == pl.Utf8:
        df = df.with_columns(pl.col("date").str.to_date())

    min_date = df.select(pl.col("date").min()).item()
    max_date = df.select(pl.col("date").max()).item()
    logger.info("Date range: %s ~ %s", min_date, max_date)
    return df


def run_eda(df: pl.DataFrame) -> dict:
    """Produce EDA charts into IMAGES_DIR. Returns a dict of chart filenames."""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    charts = []

    # 1. Behavior distribution pie
    behavior_pd = (
        df.group_by("behavior_type")
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
        .to_pandas()
    )
    colors = ["#2E86AB", "#F18F01", "#A23B72", "#C73E1D"]
    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        behavior_pd["count"],
        labels=behavior_pd["behavior_type"],
        autopct="%1.1f%%",
        colors=colors,
        startangle=90,
        textprops={"fontsize": 11},
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontweight("bold")
    ax.set_title("User Behavior Distribution", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/01_behavior_pie.png", dpi=150)
    plt.close()
    charts.append("01_behavior_pie.png")
    logger.info("  ✓ 01_behavior_pie.png")

    # 2. DAU trend
    daily = (
        df.group_by("date")
        .agg(pl.col("user_id").n_unique().alias("dau"))
        .sort("date")
        .to_pandas()
    )
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(range(len(daily)), daily["dau"], marker="o", linewidth=2, color="#2E86AB")
    ax.fill_between(range(len(daily)), daily["dau"], alpha=0.2, color="#2E86AB")
    ax.set_xticks(range(len(daily)))
    ax.set_xticklabels([str(d) for d in daily["date"]], rotation=30, ha="right")
    for i, row in daily.iterrows():
        ax.annotate(
            f"{int(row['dau']):,}",
            (i, row["dau"]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=7,
        )
    ax.set_title("Daily Active Users (DAU) Trend", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/01_dau_trend_v2.png", dpi=150)
    plt.close()
    charts.append("01_dau_trend_v2.png")
    logger.info("  ✓ 01_dau_trend_v2.png")

    # 3. Hourly distribution
    hourly = (
        df.group_by("hour")
        .agg(pl.len().alias("count"))
        .sort("hour")
        .to_pandas()
    )
    fig, ax = plt.subplots(figsize=(12, 5))
    bars = ax.bar(hourly["hour"], hourly["count"], color="#2E86AB", alpha=0.8)
    peak_hour = hourly.loc[hourly["count"].idxmax(), "hour"]
    bars[int(peak_hour)].set_color("#F18F01")
    ax.set_title(
        f"User Activity by Hour (Peak: {int(peak_hour)}:00)",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xlabel("Hour")
    ax.set_ylabel("Action Count")
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/01_hourly_v2.png", dpi=150)
    plt.close()
    charts.append("01_hourly_v2.png")
    logger.info("  ✓ 01_hourly_v2.png")

    # 4. Heatmap (hour x weekday)
    pivot = df.group_by(["day_of_week", "hour"]).agg(pl.len().alias("count")).to_pandas()
    pivot_table = pivot.pivot(index="day_of_week", columns="hour", values="count").fillna(0)
    weekday_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
    pivot_table.index = [weekday_map.get(i, str(i)) for i in pivot_table.index]
    fig, ax = plt.subplots(figsize=(14, 5))
    sns.heatmap(pivot_table, cmap="YlOrRd", linewidths=0.5, ax=ax)
    ax.set_title("User Activity Heatmap (Hour × Weekday)", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/01_heatmap.png", dpi=150)
    plt.close()
    charts.append("01_heatmap.png")
    logger.info("  ✓ 01_heatmap.png")

    # 5. Weekend vs Weekday
    wend = df.group_by("is_weekend").agg(pl.len().alias("count")).to_pandas()
    wend["label"] = wend["is_weekend"].map({0: "Weekday", 1: "Weekend"})
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(wend["label"], wend["count"], color=["#2E86AB", "#F18F01"])
    for i, v in enumerate(wend["count"]):
        ax.text(i, v + max(wend["count"]) * 0.01, f"{v:,}", ha="center", fontweight="bold")
    ax.set_title("Weekend vs Weekday Activity", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/01_weekend.png", dpi=150)
    plt.close()
    charts.append("01_weekend.png")
    logger.info("  ✓ 01_weekend.png")

    return {"charts": charts}
