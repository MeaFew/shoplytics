"""Churn prediction model.

Builds user-level features from raw behavior logs, fits Logistic Regression
and XGBoost, and emits ROC / feature-importance charts. Returns model metrics
for the pipeline summary.

Split out of scripts/pipeline.py.
"""

import logging
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl
import seaborn as sns
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from config import (
    CHURN_ACTIVE_DAYS_THRESHOLD,
    IMAGES_DIR,
    RANDOM_SEED,
    TEST_SIZE,
)

logger = logging.getLogger("pipeline.churn")

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_style("whitegrid")

FEATURES = [
    "total_pv",
    "total_buy",
    "total_cart",
    "total_fav",
    "active_days",
    "active_hours",
    "recency_days",
    "weekend_ratio",
    "buy_conversion",
    "cart_conversion",
    "fav_conversion",
]


def build_user_features(df: pl.DataFrame) -> pl.DataFrame:
    """Build user-level features (reusable across stages)."""
    dataset_max_date = df.select(pl.col("date").max()).item()

    user_stats = df.group_by("user_id").agg(
        [
            pl.col("behavior_type").filter(pl.col("behavior_type") == "pv").count().alias("total_pv"),
            pl.col("behavior_type").filter(pl.col("behavior_type") == "buy").count().alias("total_buy"),
            pl.col("behavior_type").filter(pl.col("behavior_type") == "cart").count().alias("total_cart"),
            pl.col("behavior_type").filter(pl.col("behavior_type") == "fav").count().alias("total_fav"),
            pl.col("date").n_unique().alias("active_days"),
            pl.col("hour").n_unique().alias("active_hours"),
            pl.col("date").max().alias("last_date"),
            pl.col("is_weekend").mean().alias("weekend_ratio"),
        ]
    ).with_columns(
        [
            ((dataset_max_date - pl.col("last_date")).dt.total_days()).alias("recency_days"),
            (pl.col("total_buy") / (pl.col("total_pv") + 0.001)).alias("buy_conversion"),
            (pl.col("total_cart") / (pl.col("total_pv") + 0.001)).alias("cart_conversion"),
            (pl.col("total_fav") / (pl.col("total_pv") + 0.001)).alias("fav_conversion"),
        ]
    )

    user_stats = user_stats.with_columns(
        pl.when(pl.col("active_days") <= CHURN_ACTIVE_DAYS_THRESHOLD)
        .then(1)
        .otherwise(0)
        .alias("churn")
    )
    return user_stats


def run_churn_prediction(df: pl.DataFrame) -> dict:
    """Train churn models and emit charts. Returns metrics dict."""
    t1 = datetime.now()
    user_stats = build_user_features(df)

    sample_size = min(100_000, user_stats.height)
    if sample_size < user_stats.height:
        logger.info("数据量较大，采样 %s 用户进行建模", f"{sample_size:,}")
        user_pd = user_stats.sample(n=sample_size, seed=RANDOM_SEED).to_pandas()
    else:
        user_pd = user_stats.to_pandas()

    logger.info(
        "Feature matrix: %s users | Build time: %.1fs",
        f"{len(user_pd):,}",
        (datetime.now() - t1).total_seconds(),
    )

    X = user_pd[FEATURES]
    y = user_pd["churn"]
    logger.info("Churn rate: %.1f%%", y.mean() * 100)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y
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
        eval_metric="logloss",
    )
    xgbm.fit(X_train, y_train)
    y_prob_xgb = xgbm.predict_proba(X_test)[:, 1]
    y_pred_xgb = xgbm.predict(X_test)
    xgb_auc = roc_auc_score(y_test, y_prob_xgb)

    logger.info(
        "Logistic Regression: AUC=%.4f, Acc=%.4f, P=%.4f, R=%.4f, F1=%.4f",
        lr_auc,
        accuracy_score(y_test, y_pred_lr),
        precision_score(y_test, y_pred_lr),
        recall_score(y_test, y_pred_lr),
        f1_score(y_test, y_pred_lr),
    )
    logger.info(
        "XGBoost:             AUC=%.4f, Acc=%.4f, P=%.4f, R=%.4f, F1=%.4f",
        xgb_auc,
        accuracy_score(y_test, y_pred_xgb),
        precision_score(y_test, y_pred_xgb),
        recall_score(y_test, y_pred_xgb),
        f1_score(y_test, y_pred_xgb),
    )

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
    imp = (
        pl.DataFrame({"feature": FEATURES, "importance": xgbm.feature_importances_})
        .sort("importance", descending=True)
        .to_pandas()
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=imp, x="importance", y="feature", palette="viridis", ax=ax)
    ax.set_title("XGBoost Feature Importance", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(f"{IMAGES_DIR}/02_feature_importance.png", dpi=150)
    plt.close()
    logger.info("  ✓ 02_feature_importance.png")

    return {
        "lr_auc": float(lr_auc),
        "xgb_auc": float(xgb_auc),
        "charts": ["02_roc_curve.png", "02_feature_importance.png"],
    }
