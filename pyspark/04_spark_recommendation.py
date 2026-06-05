# -*- coding: utf-8 -*-
"""
04_spark_recommendation.py
PySpark 分布式推荐算法脚本（基于 ALS 矩阵分解）

功能：
    1. 读取清洗后的 Parquet 数据
    2. 构建用户-物品隐式反馈评分矩阵
    3. 使用 Spark MLlib ALS 训练矩阵分解模型
    4. 为指定用户生成 Top-N 推荐
    5. 评估模型（RMSE）
    6. 展示 Spark MLlib 的使用

大数据处理要点：
    - ALS 天然分布式，适合海量用户-物品矩阵
    - 隐式反馈场景下使用 implicitPrefs=true，配合 alpha 参数调节置信度
    - 对 user_id / item_id 进行重编码（StringIndexer 或自实现映射），
      避免原始 ID 过大导致向量维度稀疏
    - checkpoint 防止 DAG 过长导致 StackOverflow
"""

import os
import shutil
import random
import sys
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, count, sum as spark_sum, lit, when, monotonically_increasing_id
from pyspark.ml.recommendation import ALS
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.feature import StringIndexer

# 将项目根目录加入 Python 路径，确保能导入 config.py
project_root = Path(__file__).parents[1].resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config import SPARK_INPUT_PATH, SPARK_OUTPUT_DIR

# ---------------------------------------------------------------------------
# 0. 路径配置与参数
# ---------------------------------------------------------------------------
INPUT_PATH = str(SPARK_INPUT_PATH)
OUTPUT_PATH = os.path.join(str(SPARK_OUTPUT_DIR), "recommendation")

# 推荐参数
TOP_N = 10              # 为每个用户推荐 Top-N 物品
RANK = 10               # 隐因子维度
MAX_ITER = 10           # 迭代次数
REG_PARAM = 0.1         # 正则化参数
ALPHA = 40.0            # 隐式反馈置信度缩放因子
TRAIN_RATIO = 0.8       # 训练集比例

# ---------------------------------------------------------------------------

def main():
    # 1. 初始化 SparkSession
    # ---------------------------------------------------------------------------
    spark = (
        SparkSession.builder
        .appName("PDD-ALS-Recommendation")
        .master("local[*]")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .config("spark.sql.shuffle.partitions", "200")
        # ALS 迭代会产生很长的 DAG，设置 checkpoint 目录防止 StackOverflow
        .config("spark.checkpoint.dir", os.path.join(OUTPUT_PATH, "checkpoints"))
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

    # ---------------------------------------------------------------------------
    # 3. 构建用户-物品隐式反馈评分矩阵
    # ---------------------------------------------------------------------------
    print("[INFO] 构建用户-物品隐式反馈评分矩阵...")

    # 隐式反馈评分规则：
    #   pv  = 1, fav = 2, cart = 3, buy = 5
    # 该评分反映用户对物品的兴趣强度，buy 权重最高

    df_rating = (
        df
        .withColumn(
            "rating",
            when(col("behavior_type") == "pv", lit(1))
            .when(col("behavior_type") == "fav", lit(2))
            .when(col("behavior_type") == "cart", lit(3))
            .when(col("behavior_type") == "buy", lit(5))
            .otherwise(lit(1))
        )
        .groupBy("user_id", "item_id")
        .agg(spark_sum("rating").alias("rating"))   # 同一用户对同一物品的多次行为累加
        .filter(col("rating") > 0)
    )

    print(f"[INFO] 用户-物品评分矩阵行数: {df_rating.count():,}")
    print("[INFO] 评分矩阵预览:")
    df_rating.show(10, truncate=False)

    # ---------------------------------------------------------------------------
    # 4. ID 重编码（ALS 要求 user/item 为整数索引，且从 0 开始连续）
    # ---------------------------------------------------------------------------
    print("[INFO] 对 user_id 和 item_id 进行重编码...")

    # 使用 StringIndexer 将 LongType 的 ID 映射为连续整数索引
    # 注意：StringIndexer 输入为 String，因此先 cast
    df_rating = df_rating.withColumn("user_id_str", col("user_id").cast("string"))
    df_rating = df_rating.withColumn("item_id_str", col("item_id").cast("string"))

    user_indexer = StringIndexer(inputCol="user_id_str", outputCol="user_idx", handleInvalid="keep")
    item_indexer = StringIndexer(inputCol="item_id_str", outputCol="item_idx", handleInvalid="keep")

    user_indexer_model = user_indexer.fit(df_rating)
    df_rating = user_indexer_model.transform(df_rating)

    item_indexer_model = item_indexer.fit(df_rating)
    df_rating = item_indexer_model.transform(df_rating)

    # 将索引转为整数类型（ALS 要求）
    df_rating = df_rating.withColumn("user_idx", col("user_idx").cast("int"))
    df_rating = df_rating.withColumn("item_idx", col("item_idx").cast("int"))

    # 保留原始 ID 映射关系，便于后续反查
    user_id_map = df_rating.select("user_id", "user_idx").distinct()
    item_id_map = df_rating.select("item_id", "item_idx").distinct()

    print("[INFO] ID 重编码完成")

    # ---------------------------------------------------------------------------
    # 5. 划分训练集与测试集
    # ---------------------------------------------------------------------------
    print("[INFO] 划分训练集与测试集...")

    train_df, test_df = df_rating.randomSplit([TRAIN_RATIO, 1 - TRAIN_RATIO], seed=42)
    print(f"[INFO] 训练集行数: {train_df.count():,}")
    print(f"[INFO] 测试集行数: {test_df.count():,}")

    # ---------------------------------------------------------------------------
    # 6. 训练 ALS 模型
    # ---------------------------------------------------------------------------
    print("[INFO] 训练 ALS 模型...")

    als = (
        ALS()
        .setUserCol("user_idx")
        .setItemCol("item_idx")
        .setRatingCol("rating")
        .setRank(RANK)                 # 隐因子维度
        .setMaxIter(MAX_ITER)           # 最大迭代次数
        .setRegParam(REG_PARAM)         # 正则化参数
        .setAlpha(ALPHA)                # 隐式反馈置信度参数
        .setImplicitPrefs(True)         # 启用隐式反馈模式
        .setColdStartStrategy("drop")   # 冷启动时丢弃，避免 NaN 预测值
        .setNonnegative(True)           # 非负矩阵分解，增强可解释性
        .setCheckpointInterval(2)       # 每 2 次迭代 checkpoint，防止 DAG 过长
    )

    model = als.fit(train_df)
    print("[INFO] ALS 模型训练完成")

    # ---------------------------------------------------------------------------
    # 7. 模型评估（RMSE）
    # ---------------------------------------------------------------------------
    print("[INFO] 模型评估...")

    # 在测试集上进行预测
    predictions = model.transform(test_df).na.drop()  # 过滤掉冷启动产生的 NaN

    evaluator = RegressionEvaluator(
        metricName="rmse",
        labelCol="rating",
        predictionCol="prediction"
    )

    rmse = evaluator.evaluate(predictions)
    print(f"[INFO] 测试集 RMSE: {rmse:.4f}")

    # 同时计算 MAE
    evaluator_mae = RegressionEvaluator(
        metricName="mae",
        labelCol="rating",
        predictionCol="prediction"
    )
    mae = evaluator_mae.evaluate(predictions)
    print(f"[INFO] 测试集 MAE: {mae:.4f}")

    # ---------------------------------------------------------------------------
    # 8. 为指定用户生成 Top-N 推荐
    # ---------------------------------------------------------------------------
    print(f"[INFO] 为指定用户生成 Top-{TOP_N} 推荐...")

    # 获取所有用户索引
    all_users = df_rating.select("user_idx").distinct()

    # 为所有用户生成推荐（Top-N）
    user_recs = model.recommendForAllUsers(TOP_N)

    # 反查原始 user_id
    user_recs = user_recs.join(user_id_map, on="user_idx", how="inner")

    # 展开推荐列表，反查原始 item_id
    from pyspark.sql.functions import explode, struct

    user_recs_exploded = (
        user_recs
        .withColumn("rec", explode(col("recommendations")))
        .select(
            col("user_id"),
            col("rec.item_idx").alias("item_idx"),
            col("rec.rating").alias("predicted_rating")
        )
        .join(item_id_map, on="item_idx", how="inner")
        .select("user_id", "item_id", "predicted_rating")
        .orderBy("user_id", col("predicted_rating").desc())
    )

    print("[INFO] 用户推荐结果预览（前 20 条）:")
    user_recs_exploded.show(20, truncate=False)

    # 随机抽取一个用户，展示其完整 Top-N 推荐
    sample_user = user_recs_exploded.select("user_id").distinct().limit(1).collect()
    if sample_user:
        sample_user_id = sample_user[0]["user_id"]
        print(f"[INFO] 用户 {sample_user_id} 的 Top-{TOP_N} 推荐:")
        user_recs_exploded.filter(col("user_id") == sample_user_id).show(TOP_N, truncate=False)

    # ---------------------------------------------------------------------------
    # 9. 物品相似度分析（可选）：获取每个物品的最相似物品
    # ---------------------------------------------------------------------------
    print(f"[INFO] 物品相似度推荐（Top-{TOP_N} 相似物品）预览:")

    item_recs = model.recommendForAllItems(TOP_N)
    item_recs_exploded = (
        item_recs
        .withColumn("rec", explode(col("recommendations")))
        .select(
            col("item_idx"),
            col("rec.user_idx").alias("similar_item_idx"),
            col("rec.rating").alias("similarity_score")
        )
        .join(item_id_map.withColumnRenamed("item_id", "similar_item_id").withColumnRenamed("item_idx", "similar_item_idx"),
              on="similar_item_idx", how="inner")
        .join(item_id_map, on="item_idx", how="inner")
        .select("item_id", "similar_item_id", "similarity_score")
        .orderBy("item_id", col("similarity_score").desc())
    )
    item_recs_exploded.show(20, truncate=False)

    # ---------------------------------------------------------------------------
    # 10. 保存推荐结果
    # ---------------------------------------------------------------------------
    print(f"[INFO] 保存推荐结果到: {OUTPUT_PATH}")

    if os.path.exists(OUTPUT_PATH):
        shutil.rmtree(OUTPUT_PATH)

    os.makedirs(OUTPUT_PATH, exist_ok=True)

    # 10.1 用户推荐结果
    user_recs_exploded.coalesce(1).write.mode("overwrite").option("header", "true").csv(
        os.path.join(OUTPUT_PATH, "user_recommendations")
    )

    # 10.2 物品相似度结果
    item_recs_exploded.coalesce(1).write.mode("overwrite").option("header", "true").csv(
        os.path.join(OUTPUT_PATH, "item_similarities")
    )

    # 10.3 模型评估指标（保存为文本）
    with open(os.path.join(OUTPUT_PATH, "model_metrics.txt"), "w", encoding="utf-8") as f:
        f.write("ALS Model Metrics\n")
        f.write("=================\n")
        f.write(f"Rank: {RANK}\n")
        f.write(f"MaxIter: {MAX_ITER}\n")
        f.write(f"RegParam: {REG_PARAM}\n")
        f.write(f"Alpha: {ALPHA}\n")
        f.write("ImplicitPrefs: True\n")
        f.write(f"Train Ratio: {TRAIN_RATIO}\n")
        f.write(f"Test RMSE: {rmse:.4f}\n")
        f.write(f"Test MAE: {mae:.4f}\n")

    print("[INFO] 推荐结果保存完成")

    # ---------------------------------------------------------------------------
    # 11. 结束
    # ---------------------------------------------------------------------------
    spark.stop()


if __name__ == "__main__":
    main()
