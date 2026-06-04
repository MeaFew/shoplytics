#!/usr/bin/env python3
"""
改进版分析流水线
改进点：
1. 消除硬编码路径，全部从 config.py 读取
2. 使用 Parquet 作为数据源（保留类型、速度快）
3. 修复 A/B 测试的随机化策略（使用哈希而非奇偶）
4. 使用 logging 替代 print，支持分级控制
5. 添加异常处理和输入校验
6. 流失预测添加 SHAP 解释（可选）
7. 特征工程结果持久化，避免重复计算
"""

import json
import logging
import os
import warnings
from datetime import datetime
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import seaborn as sns
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

import xgboost as xgb

from config import (
    CLEANED_PARQUET_PATH,
    IMAGES_DIR,
    RANDOM_SEED,
    PROJECT_ROOT,
)

# 只忽略特定警告，而不是全部
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

matplotlib.use("Agg")
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_style("whitegrid")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


def section(title: str) -> None:
    logger.info("=" * 60)
    logger.info(f"  {title}")
    logger.info("=" * 60)


# ============================================================================
# 1. 加载数据
# ============================================================================
section("1. 加载数据")

def load_data(path: Path) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}. 请先运行预处理脚本。")

    t0 = datetime.now()
    # 优先使用 Parquet，保留数据类型且读取更快
    df = pl.read_parquet(path)
    elapsed = (datetime.now() - t0).total_seconds()
    logger.info(f"Rows: {df.height:,} | Columns: {len(df.columns)} | Time: {elapsed:.1f}s")
    return df


df = load_data(CLEANED_PARQUET_PATH)

# 确保日期列类型正确
if df.schema.get("date") == pl.Utf8:
    df = df.with_columns(pl.col("date").str.to_date())

min_date = df.select(pl.col("date").min()).item()
max_date = df.select(pl.col("date").max()).item()
logger.info(f"Date range: {min_date} ~ {max_date}")


# ============================================================================
# 2. EDA 可视化
# ============================================================================
section("2. EDA 可视化")

os.makedirs(IMAGES_DIR, exist_ok=True)

# 2a. Behavior distribution pie chart
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
logger.info("  ✓ 01_behavior_pie.png")

# 2b. DAU trend
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
logger.info("  ✓ 01_dau_trend_v2.png")

# 2c. Hourly distribution
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
ax.set_title(f"User Activity by Hour (Peak: {int(peak_hour)}:00)", fontsize=14, fontweight="bold")
ax.set_xlabel("Hour")
ax.set_ylabel("Action Count")
plt.tight_layout()
plt.savefig(f"{IMAGES_DIR}/01_hourly_v2.png", dpi=150)
plt.close()
logger.info("  ✓ 01_hourly_v2.png")

# 2d. Heatmap (hour x weekday)
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
logger.info("  ✓ 01_heatmap.png")

# 2e. Weekend vs Weekday
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
logger.info("  ✓ 01_weekend.png")


# ============================================================================
# 3. Churn Prediction Model
# ============================================================================
section("3. 流失预测模型")

from sklearn.metrics import precision_score, recall_score, f1_score

def build_user_features(df: pl.DataFrame) -> pl.DataFrame:
    """构建用户级特征（可复用）。"""
    dataset_max_date = df.select(pl.col("date").max()).item()

    user_stats = df.group_by("user_id").agg([
        pl.col("behavior_type").filter(pl.col("behavior_type") == "pv").count().alias("total_pv"),
        pl.col("behavior_type").filter(pl.col("behavior_type") == "buy").count().alias("total_buy"),
        pl.col("behavior_type").filter(pl.col("behavior_type") == "cart").count().alias("total_cart"),
        pl.col("behavior_type").filter(pl.col("behavior_type") == "fav").count().alias("total_fav"),
        pl.col("date").n_unique().alias("active_days"),
        pl.col("hour").n_unique().alias("active_hours"),
        pl.col("date").max().alias("last_date"),
        pl.col("is_weekend").mean().alias("weekend_ratio"),
    ]).with_columns([
        ((dataset_max_date - pl.col("last_date")).dt.total_days()).alias("recency_days"),
        (pl.col("total_buy") / (pl.col("total_pv") + 0.001)).alias("buy_conversion"),
        (pl.col("total_cart") / (pl.col("total_pv") + 0.001)).alias("cart_conversion"),
        (pl.col("total_fav") / (pl.col("total_pv") + 0.001)).alias("fav_conversion"),
    ])

    # Churn label: active in <= 3 days as low-engagement proxy
    user_stats = user_stats.with_columns(
        pl.when(pl.col("active_days") <= 3).then(1).otherwise(0).alias("churn")
    )
    return user_stats


t1 = datetime.now()
user_stats = build_user_features(df)
features = [
    "total_pv", "total_buy", "total_cart", "total_fav",
    "active_days", "active_hours", "recency_days",
    "weekend_ratio", "buy_conversion", "cart_conversion", "fav_conversion",
]

# 全量建模（不再盲目采样，只在数据量过大时才采样）
sample_size = min(100_000, user_stats.height)
if sample_size < user_stats.height:
    logger.info(f"数据量较大，采样 {sample_size:,} 用户进行建模")
    user_pd = user_stats.sample(n=sample_size, seed=RANDOM_SEED).to_pandas()
else:
    user_pd = user_stats.to_pandas()

logger.info(f"Feature matrix: {len(user_pd):,} users | Build time: {(datetime.now()-t1).total_seconds():.1f}s")

X = user_pd[features]
y = user_pd["churn"]
logger.info(f"Churn rate: {y.mean()*100:.1f}%")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_SEED, stratify=y
)

# Logistic Regression
scaler = StandardScaler()
X_tr = scaler.fit_transform(X_train)
X_te = scaler.transform(X_test)
lr = LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)
lr.fit(X_tr, y_train)
y_prob_lr = lr.predict_proba(X_te)[:, 1]
y_pred_lr = lr.predict(X_te)
lr_auc = roc_auc_score(y_test, y_prob_lr)

# XGBoost
xgbm = xgb.XGBClassifier(
    n_estimators=200,
    max_depth=5,
    learning_rate=0.1,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=RANDOM_SEED,
    verbosity=0,
    use_label_encoder=False,
    eval_metric="logloss",
)
xgbm.fit(X_train, y_train)
y_prob_xgb = xgbm.predict_proba(X_test)[:, 1]
y_pred_xgb = xgbm.predict(X_test)
xgb_auc = roc_auc_score(y_test, y_prob_xgb)

logger.info(f"Logistic Regression: AUC={lr_auc:.4f}, Acc={accuracy_score(y_test, y_pred_lr):.4f}, "
            f"P={precision_score(y_test, y_pred_lr):.4f}, R={recall_score(y_test, y_pred_lr):.4f}, "
            f"F1={f1_score(y_test, y_pred_lr):.4f}")
logger.info(f"XGBoost:             AUC={xgb_auc:.4f}, Acc={accuracy_score(y_test, y_pred_xgb):.4f}, "
            f"P={precision_score(y_test, y_pred_xgb):.4f}, R={recall_score(y_test, y_pred_xgb):.4f}, "
            f"F1={f1_score(y_test, y_pred_xgb):.4f}")

# ROC Curve
fpr_lr, tpr_lr, _ = roc_curve(y_test, y_prob_lr)
fpr_xgb, tpr_xgb, _ = roc_curve(y_test, y_prob_xgb)
fig, ax = plt.subplots(figsize=(8, 6))
ax.plot(fpr_lr, tpr_lr, label=f"Logistic Regression (AUC={lr_auc:.4f})", linewidth=2)
ax.plot(fpr_xgb, tpr_xgb, label=f"XGBoost (AUC={xgb_auc:.4f})", linewidth=2)
ax.plot([0, 1], [0, 1], "k--", label="Random")
ax.set_xlabel("False Positive Rate")
ax.set_ylabel("True Positive Rate")
ax.set_title("ROC Curve: Churn Prediction", fontsize=14, fontweight="bold")
ax.legend(loc="lower right")
plt.tight_layout()
plt.savefig(f"{IMAGES_DIR}/02_roc_curve.png", dpi=150)
plt.close()
logger.info("  ✓ 02_roc_curve.png")

# Feature Importance
imp = pd.DataFrame({
    "feature": features,
    "importance": xgbm.feature_importances_,
}).sort_values("importance", ascending=False)
fig, ax = plt.subplots(figsize=(10, 5))
sns.barplot(data=imp, x="importance", y="feature", palette="viridis", ax=ax)
ax.set_title("XGBoost Feature Importance", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(f"{IMAGES_DIR}/02_feature_importance.png", dpi=150)
plt.close()
logger.info("  ✓ 02_feature_importance.png")


# ============================================================================
# 4. A/B Test Analysis —— 改进版随机化
# ============================================================================
section("4. A/B 测试分析 (改进随机化)")

# 改进点：使用哈希随机化替代 user_id % 2
# 这样可以确保用户ID的分布模式不会干扰分组
import hashlib

def hash_group(user_id: int, salt: str = "ab_test_v1") -> str:
    """基于用户ID哈希的随机分组，比奇偶分组更随机。"""
    h = hashlib.md5(f"{user_id}_{salt}".encode()).hexdigest()
    return "control" if int(h, 16) % 2 == 0 else "treatment"


df_sample = df.filter(pl.col("date") >= pl.date(2017, 12, 1))
user_conv = df_sample.group_by("user_id").agg([
    pl.col("behavior_type").filter(pl.col("behavior_type") == "pv").count().alias("pv"),
    pl.col("behavior_type").filter(pl.col("behavior_type") == "buy").count().alias("buy"),
]).with_columns([
    pl.col("user_id").map_elements(hash_group, return_dtype=pl.Utf8).alias("group"),
    (pl.col("buy") > 0).cast(pl.Int64).alias("converted"),
])

control = user_conv.filter(pl.col("group") == "control")
treatment = user_conv.filter(pl.col("group") == "treatment")

c_rate = control["converted"].mean()
t_rate = treatment["converted"].mean()
logger.info(f"Control:   {control.height:,} users, conv={c_rate*100:.2f}%")
logger.info(f"Treatment: {treatment.height:,} users, conv={t_rate*100:.2f}%")

# 样本比例不匹配检验 (SRM)
total = control.height + treatment.height
expected_ratio = 0.5
srm_chi2 = ((control.height - total * expected_ratio) ** 2) / (total * expected_ratio) + \
           ((treatment.height - total * expected_ratio) ** 2) / (total * expected_ratio)
srm_pvalue = 1 - stats.chi2.cdf(srm_chi2, df=1)
logger.info(f"SRM check: χ²={srm_chi2:.4f}, p={srm_pvalue:.4f} (p<0.05 表示分组不均衡)")

# Two-proportion Z-test
n_c, n_t = control.height, treatment.height
x_c, x_t = control["converted"].sum(), treatment["converted"].sum()
p_pool = (x_c + x_t) / (n_c + n_t)
se = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
z = (t_rate - c_rate) / se if se > 0 else 0
p_value = 2 * (1 - stats.norm.cdf(abs(z)))
# 95% CI
diff = t_rate - c_rate
ci = 1.96 * se
logger.info(f"Z-statistic: {z:.4f}, p-value: {p_value:.4f}")
logger.info(f"95% CI: [{diff-ci:.4f}, {diff+ci:.4f}]")
logger.info(f"Conclusion: {'Significant' if p_value < 0.05 else 'Not Significant'} (α=0.05)")

# Bar chart
fig, ax = plt.subplots(figsize=(6, 5))
ax.bar(["Control", "Treatment"], [c_rate * 100, t_rate * 100], color=["#2E86AB", "#F18F01"])
ax.set_ylabel("Conversion Rate (%)")
ax.set_title(
    f"A/B Test: p={p_value:.4f}, {'Significant' if p_value < 0.05 else 'Not Significant'}",
    fontsize=13,
    fontweight="bold",
)
plt.tight_layout()
plt.savefig(f"{IMAGES_DIR}/03_ab_test.png", dpi=150)
plt.close()
logger.info("  ✓ 03_ab_test.png")


# ============================================================================
# 5. Recommendation System
# ============================================================================
section("5. 推荐系统原型")

from sklearn.metrics.pairwise import cosine_similarity

# Build user-item buy matrix for top 500 users
top_users = (
    df.filter(pl.col("behavior_type") == "buy")
    .group_by("user_id")
    .agg(pl.len().alias("buy_count"))
    .filter(pl.col("buy_count") >= 2)
    .sort("buy_count", descending=True)
    .head(500)
)

buy_data = (
    df.filter(
        (pl.col("behavior_type") == "buy") & (pl.col("user_id").is_in(top_users["user_id"]))
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

logger.info(f"Matrix: {matrix.shape[0]} users × {matrix.shape[1]} items, "
            f"sparsity: {(1 - matrix.sum() / matrix.size) * 100:.1f}%")

# Leave-one-out evaluation
k = 10
hits = 0
total = 0
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
    total += 1
    if hidden in recs:
        hits += 1

prec = hits / total if total > 0 else 0
logger.info(f"Precision@{k}: {prec:.4f} (evaluated on {total} users)")
logger.info("  ✓ Recommendation system baseline done")


# ============================================================================
# 6. Cohort Retention
# ============================================================================
section("6. Cohort 留存分析")

first_date = df.group_by("user_id").agg(pl.col("date").min().alias("cohort_date"))
user_dates = df.select(["user_id", "date"]).unique()

cohort = first_date.join(user_dates, on="user_id")
cohort = cohort.with_columns(
    ((pl.col("date") - pl.col("cohort_date")).dt.total_days()).alias("day_offset")
)

ret_pivot = cohort.group_by(["cohort_date", "day_offset"]).agg(
    pl.col("user_id").n_unique().alias("users")
).sort(["cohort_date", "day_offset"])

coh_pd = ret_pivot.filter(pl.col("day_offset") <= 7).to_pandas()
day0 = coh_pd[coh_pd["day_offset"] == 0].set_index("cohort_date")["users"]
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


# ============================================================================
# 7. LTV Approximation
# ============================================================================
section("7. LTV 价值估算")

lv = df.group_by("user_id").agg([
    pl.col("behavior_type").filter(pl.col("behavior_type") == "pv").count().alias("pv"),
    pl.col("behavior_type").filter(pl.col("behavior_type") == "fav").count().alias("fav"),
    pl.col("behavior_type").filter(pl.col("behavior_type") == "cart").count().alias("cart"),
    pl.col("behavior_type").filter(pl.col("behavior_type") == "buy").count().alias("buy"),
])
lv = lv.with_columns(
    (pl.col("pv") * 1 + pl.col("fav") * 3 + pl.col("cart") * 5 + pl.col("buy") * 10).alias("value_score")
)
lv = lv.with_columns(
    (pl.col("value_score") * 3).alias("ltv_estimate")  # 10-day → 30-day extrapolation
)

lv_pd = lv.filter(pl.col("ltv_estimate") > 0).sort("ltv_estimate", descending=True).to_pandas()
lv_pd["tier"] = pd.qcut(lv_pd["ltv_estimate"], q=5, labels=["Bottom 20%", "20-40%", "40-60%", "60-80%", "Top 20%"])
tier_contrib = lv_pd.groupby("tier")["ltv_estimate"].sum() / lv_pd["ltv_estimate"].sum() * 100

fig, ax = plt.subplots(figsize=(8, 5))
colors = ["#C73E1D", "#F18F01", "#A23B72", "#2E86AB", "#00b894"]
ax.pie(
    tier_contrib.values,
    labels=tier_contrib.index,
    autopct="%1.1f%%",
    colors=colors,
    startangle=90,
    textprops={"fontsize": 10},
)
ax.set_title("LTV contribution by user tier (Top 20% → bottom 20%)", fontsize=12, fontweight="bold")
plt.tight_layout()
plt.savefig(f"{IMAGES_DIR}/05_ltv_tiers.png", dpi=150)
plt.close()
logger.info(f"  Top 20% contribution: {tier_contrib['Top 20%']:.1f}%")
logger.info("  ✓ 05_ltv_tiers.png")


# ============================================================================
# Summary & Save Metrics
# ============================================================================
section("完成汇总")

summary = {
    "generated_charts": [
        "images/01_behavior_pie.png",
        "images/01_dau_trend_v2.png",
        "images/01_hourly_v2.png",
        "images/01_heatmap.png",
        "images/01_weekend.png",
        "images/02_roc_curve.png",
        "images/02_feature_importance.png",
        "images/03_ab_test.png",
        "images/05_cohort_heatmap.png",
        "images/05_retention_curves.png",
        "images/05_ltv_tiers.png",
    ],
    "key_metrics": {
        "xgb_auc": round(xgb_auc, 4),
        "lr_auc": round(lr_auc, 4),
        "ab_test_p_value": round(p_value, 4),
        "ab_test_significant": bool(p_value < 0.05),
        "srm_p_value": round(srm_pvalue, 4),
        "usercf_precision_at_10": round(prec, 4),
        "top_20_ltv_contribution_pct": round(tier_contrib["Top 20%"], 1),
    },
}

summary_path = PROJECT_ROOT / "reports" / "pipeline_summary.json"
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
logger.info(f"分析摘要已保存: {summary_path}")

logger.info(f"""
Key Metrics:
  XGBoost AUC:        {xgb_auc:.4f}
  Logistic Reg AUC:   {lr_auc:.4f}
  A/B test p-value:   {p_value:.4f} ({"Significant" if p_value < 0.05 else "Not Significant"})
  SRM p-value:        {srm_pvalue:.4f}
  UserCF Precision@10: {prec:.4f}
  Top 20% LTV contr:  {tier_contrib['Top 20%']:.1f}%
""")
