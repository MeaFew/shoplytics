# 电商用户行为数据分析平台

> 基于阿里云天池 2900 万条真实用户行为数据的全链路分析平台，覆盖数据工程、SQL 分析、统计建模、A/B 测试与交互式看板。

---

## 数据集

- **来源**：[阿里云天池 — 淘宝用户行为](https://tianchi.aliyun.com/dataset/649)
- **规模**：287,004 用户 · 2,584,151 商品 · 29,116,710 条记录 · 10 天（2017-11-24 ~ 12-03）
- **行为类型**：`pv`（点击） · `buy`（购买） · `cart`（加购） · `fav`（收藏）

---

## 快速开始

```bash
git clone https://github.com/MeaFew/ecommerce-user-analytics.git
cd ecommerce-user-analytics
pip install -r requirements.txt

# 数据预处理（Polars，2900万行加载约0.4s）
python python/scripts/01_data_preprocessing_polars.py \
  --input data/raw/UserBehavior.csv \
  --output data/processed/

# 一键运行全部分析（EDA + 流失预测 + A/B 测试 + Cohort + LTV）
python python/scripts/run_analysis_pipeline.py

# 启动交互式看板
cd dashboard && streamlit run app.py
```

---

## 核心结论

| 指标 | 数值 |
|------|------|
| 日均 DAU | 205,091 |
| 点击→购买转化率 | 2.24% |
| 点击→加购转化率 | 6.21% |
| 加购→购买转化率 | 36.04% |
| 平均次日留存率 | 73.54% |
| 零转化商品数 | 960,744 件（占 37.2%） |

> 完整分析见：[业务洞察报告](reports/business_insights_report.md)

---

## 项目结构

```
ecommerce-user-analytics/
├── sql/                          # SQL 分析（7 个脚本）
│   ├── 01_database_setup.sql     #   建表 + 索引 + 视图
│   ├── 02_user_retention.sql     #   留存分析（次日/3日/7日）
│   ├── 03_conversion_funnel.sql  #   转化漏斗 + 路径分析
│   ├── 04_rfm_model.sql          #   RFM 用户分层
│   ├── 05_ab_test_framework.sql  #   A/B 测试数据准备
│   ├── 06_anomaly_detection.sql  #   异常检测（3σ + 移动平均）
│   └── 07_product_analysis.sql   #   商品与类目分析
│
├── python/
│   ├── notebooks/                # Jupyter Notebook（5 个）
│   │   ├── 01_eda_and_visualization.ipynb  # 探索性数据分析
│   │   ├── 02_user_churn_prediction.ipynb  # 流失预测模型
│   │   ├── 03_ab_test_analysis.ipynb       # A/B 测试统计检验
│   │   ├── 04_recommendation_system.ipynb   # 协同过滤推荐
│   │   └── 05_cohort_and_ltv.ipynb         # 同期群 + LTV 估算
│   └── scripts/
│       ├── 01_data_preprocessing.py         # Pandas 预处理
│       ├── 01_data_preprocessing_polars.py  # Polars 高性能预处理
│       ├── 02_data_analysis.py              # 分析函数库
│       ├── 03_daily_report_generator.py     # 自动化日报
│       └── run_analysis_pipeline.py         # 一键运行全部分析
│
├── dbt/                          # 数据工程（三层模型 + 7 个数据质量测试）
├── pyspark/                      # 大数据处理（ETL + ALS 推荐）
├── dashboard/                    # Streamlit 交互式看板
├── images/                       # 图表输出
└── reports/                      # 分析报告
```

---

## 分析模块

| 模块 | 方法 |
|------|------|
| 数据预处理 | Polars 惰性求值，性能比 Pandas 快 60 倍 |
| 用户留存分析 | 自连接 + 窗口函数（`ROW_NUMBER` / `LAG`） |
| 转化漏斗 | CTE + 条件聚合，区分行为次数与独立用户两种口径 |
| RFM 分层 | `NTILE(5)` 分箱 + 生命周期状态迁移 |
| A/B 测试 | 两比例 Z 检验 · 卡方检验 · Cohen's h 效应量 · 95% 置信区间 |
| 流失预测 | 11 维特征工程 · 逻辑回归 vs XGBoost · ROC 评估 |
| 协同过滤推荐 | UserCF（余弦相似度） · ALS（PySpark MLlib） |
| 异常检测 | 3σ 原则 + 移动平均双重检测 · 自动化日报异常标红 |
| Cohort 同期群 | 留存热力图 + 留存衰减曲线 · 识别优质获客期 |
| LTV 估算 | 行为价值权重建模 · Top 20% 贡献约 46% 价值 |
| 交互式看板 | Streamlit + Plotly · KPI 卡片 · 漏斗 · RFM · 多维筛选 |

---

## 技术栈

| 层级 | 工具 |
|------|------|
| 数据处理 | **Polars**（Rust 内核，快 60 倍）· Pandas · **PySpark** |
| SQL 引擎 | SQLite · **DuckDB**（零配置 OLAP） |
| 数据工程 | **dbt**（模型版本控制、自动化测试、数据血缘） |
| 建模 | Scikit-learn · **XGBoost** · SciPy |
| 可视化 | Matplotlib · Seaborn · **Plotly** |
| 交付 | **Streamlit**（交互式应用）· Jupyter |

---

## 数据局限性

- **时间窗口仅 10 天**：无法观察月度/季度周期性，7 日以上留存右删失。
- **缺少金额字段**：无法计算 GMV、客单价、ARPU，RFM 退化为 RF 模型。
- **缺少用户属性**：无性别、年龄、地域、设备等维度，画像受限。
- **A/B 实验为模拟**：基于 `user_id` 奇偶分组，实际业务应使用哈希随机分组。

---

## 许可

数据集来自阿里云天池，遵循其使用协议。代码仅供学习参考。
