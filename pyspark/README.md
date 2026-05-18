# PySpark 大数据处理模块

本模块使用 **PySpark 3.x** 对阿里云天池电商用户行为数据集（约 1 亿条记录）进行分布式大数据处理，展示 Hadoop/Spark 生态的核心能力。适用于电商数据分析师岗位数据分析项目中的大数据实践展示。

---

## 目录结构

```
pyspark/
├── 01_spark_etl.py          # ETL 数据清洗与特征工程
├── 02_spark_metrics.py      # 核心指标计算（DAU、转化率、窗口函数）
├── 03_spark_user_profile.py # 用户画像构建（RFM 标签体系）
├── 04_spark_recommendation.py # ALS 矩阵分解推荐算法
└── README.md                # 本说明文档
```

---

## 环境配置要求

### 1. 前置依赖

| 组件 | 版本建议 | 说明 |
|------|---------|------|
| Java JDK | 8 或 11 | Spark 运行依赖 JVM |
| Apache Spark | 3.3.x / 3.4.x / 3.5.x | 分布式计算引擎 |
| Python | 3.8 - 3.11 | PySpark 绑定 |
| PySpark | 对应 Spark 版本 | `pip install pyspark` |

### 2. 快速安装（Windows / Linux / macOS）

```bash
# 1. 安装 Java（如未安装）
#    Windows: 下载 Oracle JDK 或 Eclipse Temurin (Adoptium)
#    Linux:   sudo apt install openjdk-11-jdk
#    macOS:   brew install openjdk@11

# 2. 验证 Java
java -version

# 3. 安装 PySpark（会自动下载对应 Spark 发行版）
pip install pyspark==3.5.0

# 4. 验证 PySpark
python -c "import pyspark; print(pyspark.__version__)"
```

> **提示**：`pip install pyspark` 会自动将 Spark 运行时下载到 Python 环境中，无需单独下载 Spark 安装包，适合本地单机调试。

### 3. 环境变量（可选）

若已独立安装 Spark，可配置环境变量：

```bash
# Linux / macOS
export SPARK_HOME=/path/to/spark
export PATH=$SPARK_HOME/bin:$PATH

# Windows (PowerShell)
$env:SPARK_HOME = "C:\path\to\spark"
$env:PATH += ";$env:SPARK_HOME\bin"
```

---

## 脚本运行方法

所有脚本均适配 **本地单机模式**（`master("local[*]")`），无需 Hadoop/YARN 集群即可运行。

### 运行顺序

建议按编号顺序执行，因为下游脚本依赖上游生成的数据：

```bash
cd E:\NewWorkProject\PDD\pdd-data-analyst-project

# 步骤 1：ETL 清洗
python pyspark/01_spark_etl.py

# 步骤 2：指标计算
python pyspark/02_spark_metrics.py

# 步骤 3：用户画像
python pyspark/03_spark_user_profile.py

# 步骤 4：推荐算法
python pyspark/04_spark_recommendation.py
```

### 数据回退机制

若不存在完整的 `data/raw/UserBehavior.csv`（1 亿条），脚本会自动回退到同目录下的 `UserBehavior_sample.csv`（样本数据），确保代码可运行。

---

## 各脚本功能说明

### `01_spark_etl.py` — ETL 数据清洗与特征工程

- **SparkSession 初始化**：本地模式，开启 AQE 自适应查询、Kryo 序列化、Snappy 压缩
- **显式 Schema 读取**：避免 CSV 无 header 时的运行时推断开销
- **数据清洗**：过滤非法 ID、异常时间戳、限定 behavior_type 取值范围，全局去重
- **时间特征衍生**：`date`, `hour`, `day_of_week`, `is_weekend`
- **行为评分映射**：`pv=1, fav=2, cart=3, buy=4`，为后续机器学习准备
- **分区存储**：按 `date` 分区写入 Parquet，提升后续日期过滤查询性能
- **DataFrame API 演示**：`select`, `filter`, `groupBy/agg`, `withColumn`

**输出**：`data/processed/spark_cleaned/`（Parquet 分区文件）

---

### `02_spark_metrics.py` — 核心指标计算

- **Spark SQL 聚合**：使用 SQL 语句计算每日 DAU、PV、购买量、加购量、收藏量
- **转化率计算**：`conversion_rate = buy_count / pv_count`
- **每小时流量分布**：`date` + `hour` 二维分组，统计事件数与独立访客数
- **7 日移动平均**：使用 `Window.rowsBetween(-6, 0)` 计算 DAU 与转化率的滑动平均，避免全表自连接
- **行为占比分析**：每日各行为类型占比，辅助理解用户行为结构

**输出**：`data/processed/spark_metrics/`（多个 CSV 文件）

---

### `03_spark_user_profile.py` — 用户画像构建

- **用户行为统计**：总行为数、PV、购买、加购、收藏、独立商品数、独立类目数
- **Recency 计算**：数据集最大日期 - 用户最近一次行为日期
- **偏好类目**：使用窗口函数 `row_number()` 取每个用户点击最多的 Top-1 类目
- **用户标签体系**（基于 RFM 简化）：
  - `高活跃`：行为数前 20% + 有购买 + 近 3 天活跃
  - `一般`：行为数前 50% + 近 7 天活跃
  - `沉睡`：7 < Recency ≤ 30 天
  - `流失`：Recency > 30 天 或 行为极少且长期未活跃
- **购买转化率**：`buy_count / pv_count`

**输出**：`data/processed/user_profile/`（Parquet + CSV）

---

### `04_spark_recommendation.py` — ALS 矩阵分解推荐

- **隐式反馈评分矩阵**：
  - `pv=1, fav=2, cart=3, buy=5`，同一用户-物品多次行为累加
- **ID 重编码**：使用 `StringIndexer` 将原始 `user_id` / `item_id` 映射为连续整数索引，满足 ALS 输入要求
- **ALS 模型训练**：
  - `implicitPrefs=True`：隐式反馈模式
  - `alpha=40.0`：置信度缩放因子
  - `nonnegative=True`：非负矩阵分解
  - `checkpointInterval=2`：防止迭代 DAG 过长导致 StackOverflow
- **模型评估**：测试集 RMSE、MAE
- **Top-N 推荐**：为所有用户生成 Top-10 物品推荐，并反查原始 ID
- **物品相似度**：`recommendForAllItems` 获取相似物品列表

**输出**：`data/processed/recommendation/`（用户推荐 CSV、物品相似度 CSV、模型指标文本）

---

## 大数据处理思路说明

### 1. 为什么使用 Spark？

电商用户行为数据集约 **1 亿条记录**，单机 Pandas 无法承载（内存溢出、处理耗时）。Spark 的分布式 DataFrame/SQL 引擎可将计算拆分到多核/多节点，配合列式存储（Parquet）实现高效分析。

### 2. 性能优化措施

| 技术点 | 应用场景 | 作用 |
|--------|---------|------|
| **AQE 自适应查询执行** | ETL、聚合 | 运行时自动优化 Join 策略与分区数 |
| **Kryo 序列化** | Shuffle、缓存 | 比 Java 序列化更紧凑，减少网络/磁盘 IO |
| **Snappy 压缩** | Parquet 写入 | 压缩率高且解压速度快 |
| **显式 Schema** | CSV 读取 | 避免额外扫描推断类型，节省一次全表读取 |
| **分区存储** | Parquet 输出 | 按 `date` 分区，后续按日期过滤可跳过无关分区 |
| **窗口函数** | 7 日移动平均 | 替代自连接，减少 Shuffle 数据量 |
| **Checkpoint** | ALS 迭代 | 截断 DAG，防止长 lineage 导致 StackOverflow |
| **coalesce(1)** | 小结果集输出 | 合并为单文件 CSV，便于查看（大数据量下不建议） |

### 3. 数据倾斜应对

- **用户级聚合倾斜**：热门用户行为记录极多。实际生产环境中可通过 **Salting**（给 key 加随机前缀）打散大 key，二次聚合后再合并。
- **ALS 隐式反馈**：通过 `alpha` 参数调节置信度，避免少数高评分样本主导模型。

### 4. 从本地到生产

本模块使用 `local[*]` 模式，便于数据分析项目演示。迁移到生产集群（YARN/K8S）时，仅需：

1. 移除 `.master("local[*]")`，提交到集群默认 Master
2. 将输入路径改为 HDFS/S3 路径：`hdfs://namenode:8020/data/...`
3. 根据集群规模调整 `spark.sql.shuffle.partitions`（通常 200-1000）
4. 使用 `spark-submit` 提交作业：
   ```bash
   spark-submit --master yarn --deploy-mode cluster pyspark/01_spark_etl.py
   ```

---

## 常见问题

**Q1: 运行时报 `Java not found`？**
> 确保已安装 JDK 8/11，且 `java -version` 可正常输出。Windows 用户需配置 `JAVA_HOME` 环境变量。

**Q2: 提示 `输入路径不存在`？**
> 脚本会自动检测 `data/raw/UserBehavior.csv` 与 `UserBehavior_sample.csv`。请确保样本数据存在于 `data/raw/` 目录下。

**Q3: ALS 训练很慢或报错 `StackOverflow`？**
> 已内置 `checkpointInterval=2` 与 `spark.checkpoint.dir` 配置。若仍报错，可减少 `MAX_ITER` 或降低 `RANK`。

**Q4: 如何查看 Spark UI？**
> 运行期间打开浏览器访问 `http://localhost:4040`，可查看 Jobs、Stages、SQL 执行计划等。

---

## 技术栈总结

- **Spark Core**：RDD 基础（本模块主要使用 DataFrame API）
- **Spark SQL**：结构化查询、临时视图、Catalyst 优化器
- **Spark DataFrame**：延迟计算、列式存储、丰富算子
- **Spark Window Functions**：滑动窗口、排名、分桶
- **Spark MLlib**：ALS 协同过滤、StringIndexer、RegressionEvaluator
- **Parquet**：列式存储、分区、压缩

---

> 作者：数据工程数据分析项目  
数据分析项目  
> 数据集：阿里云天池 — 电商用户行为数据集
