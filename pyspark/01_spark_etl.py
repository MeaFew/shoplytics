# -*- coding: utf-8 -*-
"""
01_spark_etl.py
PySpark ETL 数据清洗与特征工程脚本

功能：
    1. 初始化 SparkSession（本地模式）
    2. 读取无 header 的 CSV 原始数据
    3. 数据清洗：去重、过滤异常值、类型转换
    4. 时间戳转换为日期时间，并衍生日期特征
    5. 保存清洗后的 Parquet 格式数据

大数据处理要点：
    - 使用 DataFrame API 进行延迟计算（Lazy Evaluation），提升性能
    - 显式定义 Schema，避免运行时推断带来的额外扫描开销
    - 去重前对关键字段进行过滤，减少 Shuffle 数据量
    - Parquet 列式存储 + Snappy 压缩，兼顾查询性能与存储空间
"""

import os
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径，确保能导入 config.py
project_root = Path(__file__).parents[1].resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import RAW_CSV_PATH, PROCESSED_DATA_DIR

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, to_timestamp, from_unixtime,
    year, month, dayofmonth, hour, dayofweek,
    when, lit, count, countDistinct
)
from pyspark.sql.types import (
    StructType, StructField, LongType, StringType, IntegerType
)

# ---------------------------------------------------------------------------
# 0. 路径配置
# ---------------------------------------------------------------------------
RAW_CSV = str(RAW_CSV_PATH)
SAMPLE_CSV_PATH = str(Path(RAW_CSV).parent / "UserBehavior_sample.csv")
OUTPUT_PATH = str(PROCESSED_DATA_DIR / "spark_cleaned")

# ---------------------------------------------------------------------------

def main():
    # 1. 初始化 SparkSession
    # ---------------------------------------------------------------------------
    spark = (
        SparkSession.builder
        .appName("PDD-ETL-UserBehavior")
        .master("local[*]")                      # 本地模式，使用所有 CPU 核心
        .config("spark.sql.adaptive.enabled", "true")          # AQE 自适应查询执行
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")  # Kryo 序列化
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")
    print("[INFO] SparkSession 初始化完成")
    print(f"[INFO] Spark Version: {spark.version}")

    # ---------------------------------------------------------------------------
    # 2. 定义 Schema（显式声明，避免运行时推断）
    # ---------------------------------------------------------------------------
    schema = StructType([
        StructField("user_id", LongType(), False),
        StructField("item_id", LongType(), False),
        StructField("category_id", LongType(), False),
        StructField("behavior_type", StringType(), False),
        StructField("timestamp", LongType(), False),
    ])

    # ---------------------------------------------------------------------------
    # 3. 读取 CSV 数据
    # ---------------------------------------------------------------------------
    input_path = RAW_CSV if os.path.exists(RAW_CSV) else SAMPLE_CSV_PATH
    print(f"[INFO] 读取数据源: {input_path}")

    df_raw = (
        spark.read
        .format("csv")
        .option("header", "false")      # 无 header
        .option("inferSchema", "false") # 使用显式 schema
        .schema(schema)
        .load(input_path)
    )

    print(f"[INFO] 原始数据行数: {df_raw.count():,}")
    df_raw.printSchema()

    # ---------------------------------------------------------------------------
    # 4. 数据清洗
    # ---------------------------------------------------------------------------
    print("[INFO] 开始数据清洗...")

    # 4.1 过滤异常值：
    #     - user_id / item_id / category_id / timestamp 必须非空且大于 0
    #     - behavior_type 必须是限定值之一
    valid_behaviors = ["pv", "buy", "cart", "fav"]

    df_cleaned = (
        df_raw
        .filter(
            (col("user_id") > 0) &
            (col("item_id") > 0) &
            (col("category_id") > 0) &
            (col("timestamp") > 0) &
            (col("behavior_type").isin(valid_behaviors))
        )
        # 4.2 去重：基于全部字段去重，避免重复记录干扰指标计算
        .dropDuplicates(["user_id", "item_id", "category_id", "behavior_type", "timestamp"])
    )

    # 4.3 类型转换：timestamp 从 Unix 秒级转为 Timestamp 类型
    df_cleaned = df_cleaned.withColumn(
        "event_time",
        to_timestamp(from_unixtime(col("timestamp")))
    )

    print(f"[INFO] 清洗后数据行数: {df_cleaned.count():,}")

    # ---------------------------------------------------------------------------
    # 5. 衍生特征工程
    # ---------------------------------------------------------------------------
    print("[INFO] 开始特征工程...")

    df_featured = (
        df_cleaned
        # 日期相关特征
        .withColumn("date", col("event_time").cast("date"))          # 日期
        .withColumn("year", year(col("event_time")))                 # 年
        .withColumn("month", month(col("event_time")))                # 月
        .withColumn("day", dayofmonth(col("event_time")))            # 日
        .withColumn("hour", hour(col("event_time")))                  # 小时
        .withColumn("day_of_week", dayofweek(col("event_time")))      # 星期几 (1=Sunday, 7=Saturday)
        # 是否周末：周六(7) 或 周日(1)
        .withColumn("is_weekend", when(col("day_of_week").isin(1, 7), lit(1)).otherwise(lit(0)))
        # 行为类型数值化（便于后续机器学习使用）
        .withColumn("behavior_score",
            when(col("behavior_type") == "pv", lit(1))
            .when(col("behavior_type") == "fav", lit(2))
            .when(col("behavior_type") == "cart", lit(3))
            .when(col("behavior_type") == "buy", lit(4))
            .otherwise(lit(0))
        )
    )

    # ---------------------------------------------------------------------------
    # 6. 展示 Spark DataFrame 核心操作
    # ---------------------------------------------------------------------------
    print("[INFO] === DataFrame 操作示例 ===")

    # 6.1 select：选取特定列
    df_select = df_featured.select("user_id", "behavior_type", "date", "hour")
    print("[DEMO] select 结果（前5行）:")
    df_select.show(5, truncate=False)

    # 6.2 filter：条件过滤
    df_filter = df_featured.filter((col("behavior_type") == "buy") & (col("is_weekend") == 1))
    print(f"[DEMO] filter 结果 - 周末购买行为数: {df_filter.count():,}")

    # 6.3 groupBy + agg：分组聚合
    print("[DEMO] groupBy + agg 结果 - 各行为类型统计:")
    (
        df_featured
        .groupBy("behavior_type")
        .agg(
            count("*").alias("total_count"),
            countDistinct("user_id").alias("unique_users"),
            countDistinct("item_id").alias("unique_items")
        )
        .orderBy(col("total_count").desc())
        .show(truncate=False)
    )

    # 6.4 withColumn：新增列（已在特征工程中展示）
    print("[DEMO] withColumn 结果 - 新增特征后的 Schema:")
    df_featured.printSchema()

    # ---------------------------------------------------------------------------
    # 7. 保存清洗后的数据（Parquet 格式）
    # ---------------------------------------------------------------------------
    print(f"[INFO] 保存清洗数据到 Parquet: {OUTPUT_PATH}")

    # 删除已存在的输出目录（Spark 不允许覆盖）
    import shutil
    if os.path.exists(OUTPUT_PATH):
        shutil.rmtree(OUTPUT_PATH)

    # 以 date 为分区键进行分区存储，便于后续按日期过滤查询
    # 注意：若 date 基数过大（如亿级），则不宜分区；此处样本数据量适中，可演示分区
    df_featured.write \
        .mode("overwrite") \
        .partitionBy("date") \
        .parquet(OUTPUT_PATH)

    print("[INFO] Parquet 数据保存完成")

    # ---------------------------------------------------------------------------
    # 8. 验证输出
    # ---------------------------------------------------------------------------
    df_verify = spark.read.parquet(OUTPUT_PATH)
    print(f"[INFO] 验证读取 - Parquet 数据行数: {df_verify.count():,}")
    print("[INFO] 验证读取 - Parquet Schema:")
    df_verify.printSchema()

    # ---------------------------------------------------------------------------
    # 9. 结束
    # ---------------------------------------------------------------------------
    spark.stop()


if __name__ == "__main__":
    main()
