# -*- coding: utf-8 -*-
"""
02_spark_metrics.py
PySpark 核心指标计算脚本

功能：
    1. 读取清洗后的 Parquet 数据
    2. 使用 Spark SQL 计算每日 DAU、PV、购买量、加购量、收藏量
    3. 计算每日转化率（购买 / PV）
    4. 计算每小时流量分布
    5. 使用 Spark 窗口函数计算 7 日移动平均 DAU
    6. 结果保存为 CSV

大数据处理要点：
    - Spark SQL 适合复杂的多表聚合与关联场景，执行计划可优化
    - 窗口函数（Window）避免全表自连接，降低 Shuffle 开销
    - 对日期等高频过滤字段进行分区读取，减少 IO
"""

import os
import shutil
import sys
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, count, countDistinct, sum as spark_sum, avg,
    round, lit, when, row_number, rank
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
OUTPUT_PATH = os.path.join(str(SPARK_OUTPUT_DIR), "spark_metrics")

# ---------------------------------------------------------------------------

def main():
    # 1. 初始化 SparkSession
    # ---------------------------------------------------------------------------
    spark = (
        SparkSession.builder
        .appName("PDD-Metrics-Computation")
        .master("local[*]")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
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

    # 注册临时视图，供 Spark SQL 使用
    df.createOrReplaceTempView("user_behavior")

    # ---------------------------------------------------------------------------
    # 3. 每日核心指标计算（Spark SQL）
    # ---------------------------------------------------------------------------
    print("[INFO] 计算每日核心指标...")

    # 使用 Spark SQL 进行多维度聚合，代码可读性高，且 Catalyst 优化器可生成高效执行计划
    daily_metrics_sql = """
    SELECT
        date,
        COUNT(DISTINCT user_id) AS dau,              -- 日活跃用户
        COUNT(*) AS total_pv,                        -- 总行为数（此处全部记录视为曝光/行为）
        SUM(CASE WHEN behavior_type = 'pv'    THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'buy'   THEN 1 ELSE 0 END) AS buy_count,
        SUM(CASE WHEN behavior_type = 'cart'  THEN 1 ELSE 0 END) AS cart_count,
        SUM(CASE WHEN behavior_type = 'fav'   THEN 1 ELSE 0 END) AS fav_count
    FROM user_behavior
    GROUP BY date
    ORDER BY date
    """

    df_daily = spark.sql(daily_metrics_sql)

    # 计算转化率：购买量 / PV 量（注意处理除零）
    df_daily = df_daily.withColumn(
        "conversion_rate",
        when(col("pv_count") > 0, round(col("buy_count") / col("pv_count") * 100, 4)).otherwise(lit(0.0))
    )

    print("[INFO] 每日核心指标预览:")
    df_daily.show(10, truncate=False)

    # ---------------------------------------------------------------------------
    # 4. 每小时流量分布（DataFrame API）
    # ---------------------------------------------------------------------------
    print("[INFO] 计算每小时流量分布...")

    df_hourly = (
        df
        .groupBy("date", "hour")
        .agg(
            count("*").alias("total_events"),
            countDistinct("user_id").alias("hourly_uv"),
            spark_sum(when(col("behavior_type") == "pv", 1).otherwise(0)).alias("pv_count"),
            spark_sum(when(col("behavior_type") == "buy", 1).otherwise(0)).alias("buy_count")
        )
        .orderBy("date", "hour")
    )

    print("[INFO] 每小时流量分布预览:")
    df_hourly.show(10, truncate=False)

    # ---------------------------------------------------------------------------
    # 5. 7 日移动平均 DAU（窗口函数）
    # ---------------------------------------------------------------------------
    print("[INFO] 计算 7 日移动平均 DAU...")

    # 定义窗口：按日期排序，前 6 行到当前行（共 7 天）
    window_7d = Window.orderBy("date").rowsBetween(-6, 0)

    df_daily_ma = df_daily.withColumn(
        "dau_7d_ma",
        round(avg(col("dau")).over(window_7d), 2)
    )

    # 同时计算 7 日移动平均转化率
    df_daily_ma = df_daily_ma.withColumn(
        "conversion_rate_7d_ma",
        round(avg(col("conversion_rate")).over(window_7d), 4)
    )

    print("[INFO] 7 日移动平均 DAU 预览:")
    df_daily_ma.select("date", "dau", "dau_7d_ma", "conversion_rate", "conversion_rate_7d_ma").show(15, truncate=False)

    # ---------------------------------------------------------------------------
    # 6. 行为类型占比分析（每日）
    # ---------------------------------------------------------------------------
    print("[INFO] 计算每日行为类型占比...")

    df_behavior_ratio = (
        df
        .groupBy("date", "behavior_type")
        .agg(count("*").alias("behavior_count"))
        .withColumn(
            "total_daily",
            spark_sum("behavior_count").over(Window.partitionBy("date"))
        )
        .withColumn(
            "ratio",
            round(col("behavior_count") / col("total_daily") * 100, 2)
        )
        .orderBy("date", col("behavior_count").desc())
    )

    print("[INFO] 每日行为类型占比预览:")
    df_behavior_ratio.show(10, truncate=False)

    # ---------------------------------------------------------------------------
    # 7. 保存结果到 CSV
    # ---------------------------------------------------------------------------
    print(f"[INFO] 保存指标结果到: {OUTPUT_PATH}")

    if os.path.exists(OUTPUT_PATH):
        shutil.rmtree(OUTPUT_PATH)

    # 创建输出目录
    os.makedirs(OUTPUT_PATH, exist_ok=True)

    # 7.1 每日核心指标
    df_daily_ma.coalesce(1).write.mode("overwrite").option("header", "true").csv(
        os.path.join(OUTPUT_PATH, "daily_metrics")
    )

    # 7.2 每小时流量分布
    df_hourly.coalesce(1).write.mode("overwrite").option("header", "true").csv(
        os.path.join(OUTPUT_PATH, "hourly_distribution")
    )

    # 7.3 7 日移动平均（已合并到 daily_metrics 中，此处单独保存一份窗口分析结果）
    df_daily_ma.coalesce(1).write.mode("overwrite").option("header", "true").csv(
        os.path.join(OUTPUT_PATH, "daily_metrics_with_ma")
    )

    # 7.4 行为类型占比
    df_behavior_ratio.coalesce(1).write.mode("overwrite").option("header", "true").csv(
        os.path.join(OUTPUT_PATH, "behavior_ratio")
    )

    print("[INFO] 所有指标结果保存完成")

    # ---------------------------------------------------------------------------
    # 8. 结束
    # ---------------------------------------------------------------------------
    spark.stop()


if __name__ == "__main__":
    main()
