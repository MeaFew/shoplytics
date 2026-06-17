"""
项目全局配置管理
支持通过环境变量覆盖默认值
"""

import os
from pathlib import Path

# 项目根目录（自动推导，不硬编码）
PROJECT_ROOT = Path(__file__).parent.resolve()

# 数据目录
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# 输出目录
REPORTS_DIR = PROJECT_ROOT / "reports"
IMAGES_DIR = PROJECT_ROOT / "images"

# 数据文件路径
RAW_CSV_PATH = RAW_DATA_DIR / "UserBehavior.csv"
CLEANED_CSV_PATH = PROCESSED_DATA_DIR / "user_behavior_cleaned.csv"
CLEANED_PARQUET_PATH = PROCESSED_DATA_DIR / "user_behavior_cleaned.parquet"

# DuckDB 分析数据库
DUCKDB_PATH = PROCESSED_DATA_DIR / "analytics.duckdb"

# PySpark 路径
SPARK_INPUT_PATH = PROCESSED_DATA_DIR / "spark_cleaned"
SPARK_OUTPUT_DIR = PROCESSED_DATA_DIR

def ensure_dirs() -> None:
    """创建项目所需的所有目录（不自动执行，需显式调用）。"""
    for d in [RAW_DATA_DIR, PROCESSED_DATA_DIR, REPORTS_DIR, IMAGES_DIR]:
        d.mkdir(parents=True, exist_ok=True)

# 分析参数
RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))
TEST_SIZE = float(os.getenv("TEST_SIZE", "0.2"))  # 模型训练测试集比例

# 时间范围（数据集时间窗口）
START_DATE = "2017-11-24"
END_DATE = "2017-12-03"

# Churn label definition (time-split, leakage-free):
#   Features are built from behavior in the OBSERVATION window below.
#   Label = whether the user is INACTIVE in the prediction window that follows
#   (i.e. no behavior of any kind during the prediction window -> churn=1).
# This decouples the label from the features: `active_days` in FEATURES refers
# to observation-window active days only, while the label is derived from a
# disjoint future window the features cannot see.
# Historical note: a previous version defined churn as active_days<=N over the
# full window with active_days also a feature, which leaked the label and
# produced AUC=1.0. See scripts/churn_prediction.py.
CHURN_OBSERVATION_END = os.getenv(
    "CHURN_OBSERVATION_END", "2017-12-01"
)  # observation window is [START_DATE, CHURN_OBSERVATION_END]
CHURN_PREDICTION_END = os.getenv(
    "CHURN_PREDICTION_END", END_DATE
)  # prediction window is (CHURN_OBSERVATION_END, CHURN_PREDICTION_END]

# LTV 行为权重（业务定义，可配置）
BEHAVIOR_WEIGHTS = {
    "pv": 1,
    "fav": 3,
    "cart": 5,
    "buy": 10,
}

# A/B 测试参数
AB_TEST_SPLIT_DATE = "2017-12-01"  # A/B测试分组日期
AB_TEST_SIGNIFICANCE_LEVEL = 0.05  # A/B测试显著性水平
