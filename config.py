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

# 确保目录存在
for d in [RAW_DATA_DIR, PROCESSED_DATA_DIR, REPORTS_DIR, IMAGES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 分析参数
RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))
TEST_SIZE = float(os.getenv("TEST_SIZE", "0.2"))
CHURN_ACTIVE_DAYS_THRESHOLD = int(os.getenv("CHURN_ACTIVE_DAYS_THRESHOLD", "3"))

# 时间范围（数据集时间窗口）
START_DATE = "2017-11-24"
END_DATE = "2017-12-03"

# LTV 行为权重（业务定义，可配置）
BEHAVIOR_WEIGHTS = {
    "pv": 1,
    "fav": 3,
    "cart": 5,
    "buy": 10,
}

# A/B 测试参数
AB_TEST_SPLIT_DATE = "2017-12-01"
AB_TEST_SIGNIFICANCE_LEVEL = 0.05
