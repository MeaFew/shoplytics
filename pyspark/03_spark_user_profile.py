# -*- coding: utf-8 -*-
"""
03_spark_user_profile.py
PySpark 用户画像构建脚本

功能：
    1. 读取清洗后的 Parquet 数据
    2. 聚合每个用户的行为统计特征（点击、购买、加购、收藏）
    3. 计算用户最近一次行为时间（Recency）
    4. 计算用户偏好类目（点击最多的类目）
    5. 基于 RFM 思想将用户打上标签：高活跃 / 一般 / 沉睡 / 流失
    6. 保存用户画像到 Parquet 及 CSV

大数据处理要点：
    - 用户级聚合通常涉及大 key（热门用户），可通过 salting 缓解数据倾斜
    - 使用 approx_count_distinct 替代 countDistinct 在超大规模下提升性能
    - 窗口函数 row_number() 用于取每个用户 top-1 偏好类目，避免全排序
"""

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, count, countDistinct, sum as spark_sum, max as spark_max,
    when, lit, row_number, datediff, current_date, ntile
)
from pyspark.sql.window import Window

# 将项目根目录加入 Python 路径，确保能导入 config.py
project_root = Path(__file__).parents[1].resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import SPARK_INPUT_PATH, SPARK_OUTPUT_DIR

# ---------------------------------------------------------------------------
# 0. 路径配置
# ---------------------------------------------------------------------------
INPUT_PATH = str(SPARK_INPUT_PATH)
OUTPUT_PATH = os.path.join(str(SPARK_OUTPUT_DIR), "user_profile")

# ---------------------------------------------------------------------------

def main():
    # 1. 初始化 SparkSession
    # ---------------------------------------------------------------------------
    spark = (
        SparkSession.builder
        .appName("PDD-User-Profile")
        .master("local[*]")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .config("spark.sql.shuffle.partitions", "200")  # 根据数据量调整 Shuffle 分区数
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")
    print("[INFO] SparkSession 初始化完成")

    # ---------------------------------------------------------------------------
    # 2. 读取清洗后的 Parquet 数据
    # ---------------------------------------------------------------------------
    print(f"[INFO] 读取 Parquet 数据: {INPUT_PATH}")

    if not os.path.exists(INPUT_PATH):
        print(f"[ERROR] 输入路径不存在: {INPUT_PATH}")
        print("[HINT] 请先运行 01_spark_etl.py 生成清洗数据")
        spark.stop()
        exit(1)

    df = spark.read.parquet(INPUT_PATH)
    print(f"[INFO] 读取数据行数: {df.count():,}")

    # 获取数据集中的最大日期（作为 Recency 计算的参考日期）
    max_date_row = df.agg(spark_max("date").alias("max_date")).collect()[0]
    reference_date = max_date_row["max_date"]
    print(f"[INFO] 数据集最大日期（参考日期）: {reference_date}")

    # ---------------------------------------------------------------------------
    # 3. 用户行为统计特征聚合
    # ---------------------------------------------------------------------------
    print("[INFO] 聚合用户行为统计特征...")

    # 按 user_id 聚合，计算各类行为次数
    df_user_stats = (
        df
        .groupBy("user_id")
        .agg(
            count("*").alias("total_actions"),
            spark_sum(when(col("behavior_type") == "pv", 1).otherwise(0)).alias("pv_count"),
            spark_sum(when(col("behavior_type") == "buy", 1).otherwise(0)).alias("buy_count"),
            spark_sum(when(col("behavior_type") == "cart", 1).otherwise(0)).alias("cart_count"),
            spark_sum(when(col("behavior_type") == "fav", 1).otherwise(0)).alias("fav_count"),
            spark_max("date").alias("last_active_date"),          # 最近一次行为日期
            countDistinct("item_id").alias("unique_items"),        # 交互过的商品数
            countDistinct("category_id").alias("unique_categories") # 交互过的类目数
        )
    )

    # 计算 Recency：参考日期 - 最近一次行为日期
    df_user_stats = df_user_stats.withColumn(
        "recency_days",
        datediff(lit(reference_date), col("last_active_date"))
    )

    print("[INFO] 用户行为统计特征预览:")
    df_user_stats.show(10, truncate=False)

    # ---------------------------------------------------------------------------
    # 4. 用户偏好类目（点击最多的类目）
    # ---------------------------------------------------------------------------
    print("[INFO] 计算用户偏好类目...")

    # 4.1 统计每个用户在每个类目下的点击次数
    df_category_pv = (
        df
        .filter(col("behavior_type") == "pv")
        .groupBy("user_id", "category_id")
        .agg(count("*").alias("category_pv_count"))
    )

    # 4.2 使用窗口函数取每个用户点击最多的类目（top 1）
    window_user = Window.partitionBy("user_id").orderBy(col("category_pv_count").desc())

    df_preferred_category = (
        df_category_pv
        .withColumn("rn", row_number().over(window_user))
        .filter(col("rn") == 1)
        .select("user_id", "category_id", "category_pv_count")
        .withColumnRenamed("category_id", "preferred_category")
        .withColumnRenamed("category_pv_count", "preferred_category_pv")
    )

    print("[INFO] 用户偏好类目预览:")
    df_preferred_category.show(10, truncate=False)

    # ---------------------------------------------------------------------------
    # 5. 合并用户画像基础表
    # ---------------------------------------------------------------------------
    df_profile = df_user_stats.join(df_preferred_category, on="user_id", how="left")

    # ---------------------------------------------------------------------------
    # 6. 用户标签体系（基于 RFM 思想简化版）
    # ---------------------------------------------------------------------------
    print("[INFO] 构建用户标签...")

    # 标签规则：
    #   高活跃：总行为数 >= 80% 分位点 且 购买数 > 0 且 Recency <= 3 天
    #   一般：   总行为数 >= 50% 分位点 且 Recency <= 7 天
    #   沉睡：   Recency > 7 天 且 Recency <= 30 天
    #   流失：   Recency > 30 天 或 总行为数极少（< 10% 分位点 且 Recency > 7）

    # 使用 ntile(10) 计算十分位数，避免 collect() 回传全量数据到 Driver
    # 对于小样本数据，也可使用 approxQuantile；此处演示窗口函数分桶
    window_all = Window.orderBy(col("total_actions"))
    window_all_recency = Window.orderBy(col("recency_days"))

    df_profile = (
        df_profile
        .withColumn("action_decile", ntile(10).over(window_all))      # 行为数十分位 (1=最少, 10=最多)
        .withColumn("recency_decile", ntile(10).over(window_all_recency))  # Recency 十分位 (1=最近, 10=最久)
    )

    # 定义标签逻辑
    df_profile = df_profile.withColumn(
        "user_label",
        when(
            (col("action_decile") >= 8) & (col("buy_count") > 0) & (col("recency_days") <= 3),
            lit("高活跃")
        ).when(
            (col("action_decile") >= 5) & (col("recency_days") <= 7),
            lit("一般")
        ).when(
            (col("recency_days") > 7) & (col("recency_days") <= 30),
            lit("沉睡")
        ).when(
            (col("recency_days") > 30) | ((col("action_decile") <= 2) & (col("recency_days") > 7)),
            lit("流失")
        ).otherwise(lit("一般"))
    )

    # 计算购买转化率
    df_profile = df_profile.withColumn(
        "buy_conversion_rate",
        when(col("pv_count") > 0, round(col("buy_count") / col("pv_count"), 4)).otherwise(lit(0.0))
    )

    print("[INFO] 用户画像标签分布:")
    df_profile.groupBy("user_label").count().orderBy(col("count").desc()).show(truncate=False)

    print("[INFO] 用户画像完整预览:")
    df_profile.select(
        "user_id", "total_actions", "pv_count", "buy_count", "cart_count", "fav_count",
        "recency_days", "preferred_category", "user_label", "buy_conversion_rate"
    ).show(10, truncate=False)

    # ---------------------------------------------------------------------------
    # 7. 保存用户画像
    # ---------------------------------------------------------------------------
    print(f"[INFO] 保存用户画像到: {OUTPUT_PATH}")

    if os.path.exists(OUTPUT_PATH):
        shutil.rmtree(OUTPUT_PATH)

    os.makedirs(OUTPUT_PATH, exist_ok=True)

    # 保存为 Parquet（列式存储，适合后续机器学习读取）
    df_profile.write.mode("overwrite").parquet(os.path.join(OUTPUT_PATH, "user_profile.parquet"))

    # 保存为 CSV（便于人工查看）
    df_profile.coalesce(1).write.mode("overwrite").option("header", "true").csv(
        os.path.join(OUTPUT_PATH, "user_profile_csv")
    )

    print("[INFO] 用户画像保存完成")

    # ---------------------------------------------------------------------------
    # 8. 结束
    # ---------------------------------------------------------------------------
    spark.stop()


if __name__ == "__main__":
    main()
