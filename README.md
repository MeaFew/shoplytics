<p align="center">
  <h1 align="center">E-commerce User Behavior Analytics</h1>
  <p align="center">
    <b>基于 2,900 万条真实淘宝用户行为记录的完整数据分析管线</b><br/>
    <sub>覆盖数据工程 · SQL 分析 · 统计建模 · A/B 测试 · 交互式交付</sub>
  </p>
  <p align="center">
    <a href="https://github.com/MeaFew/ecommerce-user-analytics/actions"><img src="https://github.com/MeaFew/ecommerce-user-analytics/workflows/CI/badge.svg" alt="CI"></a>
    <img src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/code%20style-ruff-000000?logo=ruff&logoColor=white" alt="Ruff">
    <img src="https://img.shields.io/badge/engine-DuckDB-FFF000?logo=duckdb&logoColor=black" alt="DuckDB">
    <img src="https://img.shields.io/badge/de-Streamlit-FF4B4B?logo=streamlit&logoColor=white" alt="Streamlit">
    <a href="https://meafew.github.io/ecommerce-user-analytics/"><img src="https://img.shields.io/badge/pages-live-blue?logo=githubpages&logoColor=white" alt="GitHub Pages"></a>
    <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  </p>
  <p align="center">
    <b>中文</b> | <a href="./README.en.md">English</a>
  </p>
</p>

---

## 项目亮点

- **量级**：在单机上以 **~0.4 秒**完成 2,900 万行数据的清洗与特征工程（Polars 向量化执行）
- **工程化**：dbt 数据模型分层（staging → intermediate → marts）+ 7 项数据质量测试 + GitHub Actions 三检查（lint / sql-lint / docker-build）
- **方法论完整**：从用户留存、转化漏斗、RFM 分群到 A/B 测试、流失预测、协同过滤推荐，覆盖用户生命周期全链路
- **生产级思考**：每个分析模块均附带「局限 → 生产化路径」的完整推演，而非停留在 toy example

---

## 数据

| 属性 | 值 |
|------|-----|
| **来源** | 阿里云天池 —「淘宝用户行为」公开数据集 |
| **规模** | 287,004 用户 · 2,584,151 商品 · **29,116,710 条记录** |
| **时间窗口** | 时间戳覆盖 2017-04 ~ 2018-01 共 84 天；**99.96% 数据集中在 2017-11-25 ~ 2017-12-03（9 天）** |
| **行为类型** | `pv`（浏览）· `buy`（购买）· `cart`（加购）· `fav`（收藏） |

> 秒级时间戳支持精细的行为序列建模；2,900 万行规模为验证 Polars / DuckDB 等现代分析工具的大吞吐性能提供了充足的实验场。

---

## 快速开始

```bash
git clone https://github.com/MeaFew/ecommerce-user-analytics.git
cd ecommerce-user-analytics

# 安装依赖并运行完整管线
make setup
make all

# 启动交互式看板
make dashboard

# 启动 Apache Superset BI 看板（需 Docker）
docker compose -f docker-compose.superset.yml up -d
# 访问 http://localhost:8088，用户名 admin / 密码 admin

# 本地质量门（与 CI 完全对齐）
make verify
```

---

## 核心指标一览

| 指标 | 值 | 业务解读 |
|------|-----|---------|
| 日均 DAU | 205,091 | 9 天核心窗口期间活跃用户规模稳定 |
| PV → 购买转化率 | **2.24%** | 典型电商水平，优化空间在于首页推荐精准度 |
| PV → 加购转化率 | 6.21% | 商品详情页设计对加购引导有效 |
| 加购 → 购买转化率 | **36.04%** | 购物车召回（短信/推送）是高 ROI 优化点 |
| 次日留存率 | 73.54% | 新用户首周留存健康 |
| 零转化商品占比 | 37.2%（960,744 件）| 长尾商品流量枯竭，需优化推荐长尾分发策略 |

> 完整业务洞察报告：[reports/business_insights_report.md](reports/business_insights_report.md)

---

## 技术架构

```
                  ┌─────────────────┐
                  │  UserBehavior   │
                  │   CSV (29M)     │
                  └────────┬────────┘
                           │ Polars ETL (~0.4s)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      DuckDB / Parquet                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ SQL Analysis│  │ dbt Models  │  │   PySpark (MLlib)   │  │
│  │ 7 scripts   │  │ staging →   │  │   ALS 矩阵分解      │  │
│  │             │  │ intermediate│  │   (分布式)          │  │
│  │             │  │ → marts     │  │                     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼────────────────────┼─────────────┘
          │                │                    │
          ▼                ▼                    ▼
   ┌────────────┐   ┌────────────┐      ┌────────────┐
   │  XGBoost   │   │  Streamlit │      │  Jupyter   │
   │ Churn Model│   │ Dashboard  │      │ Notebooks  │
   │ (11 feats) │   │ (KPI/R/F/M)│      │ (EDA/AB/   │
   │ AUC = 0.84 │   │            │      │  Cohort)   │
   └────────────┘   └────────────┘      └────────────┘
```

---

## 十大分析模块

| # | 模块 | 核心技术 | 产出价值 |
|---|------|---------|---------|
| 1 | **用户留存分析** | Self-join + 窗口函数 `ROW_NUMBER` / `LAG` | D1/D3/D7 留存曲线，识别流失拐点 |
| 2 | **转化漏斗** | CTE + 条件聚合 + 路径分类 | 四步漏斗（PV → 收藏/加购 → 购买），定位最大 leak |
| 3 | **RFM 用户分群** | `NTILE(5)` 分箱 + 生命周期状态迁移 | 8 类用户画像（冠军/忠诚/新客/流失预警等） |
| 4 | **A/B 测试框架** | 双比例 Z 检验 · 卡方检验 · Cohen's h · 95% CI | 完整的实验统计管线：样本量计算 → 同质性校验 → 效应量估计 |
| 5 | **流失预测** | XGBoost vs 逻辑回归 · 11 维特征工程 · ROC-AUC | AUC = 0.84，精准识别高风险用户 |
| 6 | **推荐系统** | UserCF（余弦相似度）· ALS（PySpark MLlib） | 协同过滤 + 矩阵分解双方案对比 |
| 7 | **异常检测** | 3σ 规则 + 移动平均 | 自动化日报 + 异常行为告警 |
| 8 | **Cohort & LTV** |  cohort 留存热力图 · 行为加权价值估计 | 用户群组生命周期价值追踪 |
| 9 | **交互看板** | Streamlit + Plotly · KPI 卡片 · 漏斗 · RFM | 产品/运营团队的自助分析工具 |
| 10 | **数据工程** | dbt 模型分层 · 7 项数据质量测试 | 可版本控制的分析数据管线 |

---

## 技术栈

| 层级 | 工具 | 选型理由 |
|------|------|---------|
| 数据处理 | **Polars**（Rust 核心）· Pandas · **PySpark** | Polars 在 29M 行数据上比 Pandas 快 60 倍；PySpark 用于 ALS 分布式矩阵分解 |
| SQL 引擎 | **DuckDB** | 零配置、列式 OLAP，单节点即可秒级聚合 29M 行 |
| 数据工程 | **dbt** | 模型版本化、血缘追踪、自动化测试，将分析 SQL 从脚本升级为工程化管线 |
| 统计建模 | scikit-learn · **XGBoost** · SciPy · statsmodels | XGBoost 处理高维稀疏特征；statsmodels 提供经典统计推断 |
| 可视化 | Matplotlib · Seaborn · **Plotly** | Plotly 交互式图表直接嵌入 Streamlit |
| 交付 | **Streamlit** · **Apache Superset** · Jupyter | Streamlit 做轻量自助看板；Superset（Docker）做企业级 BI 探查 |
| 质量保障 | pytest · **ruff** · sqlfluff · GitHub Actions | CI 全绿 = 代码规范 + SQL 规范 + Docker 构建三重校验 |

---

## 局限与生产化路径

| 局限 | 影响 | 生产化方案 |
|------|------|-----------|
| 约 9 天有效窗口 | 无法观察月度季节性；D7+ 留存右删失 | 扩展至 ≥90 天数据，引入 Prophet / ARIMA 预测 |
| 无金额字段 | GMV、ARPU、CLV 无法计算；RFM 退化为 RF | 关联订单/交易表，补全 monetary 维度 |
| 无用户属性 | 缺失 demographics、设备、渠道分段 | 关联用户画像表，支持多维 cohort 分析 |
| A/B 测试为模拟 | 基于用户 ID 哈希的随机化分组 | 哈希随机化 + SRM 校验 + CUPED 方差缩减 |
| 单节点执行 | DuckDB + 本地 Parquet | Hive / Spark on 分区 Parquet + Airflow 调度 |

> A/B 测试框架实现了完整的统计管线（样本量计算 → 同质性校验 → 双比例 Z 检验 → Cohen's h → 95% CI）——哈希分组是真实实验元数据不可获取时的**有效**随机化策略，统计方法论可直接迁移至生产实验平台（如内部 AB 平台或 Optimizely）。

---

## 项目结构

```
ecommerce-user-analytics/
├── scripts/                      # Python 工具脚本
│   ├── preprocess.py             #   Polars ETL（~0.4s / 29M rows）
│   ├── pipeline.py               #   完整分析管线编排
│   ├── run_sql.py                #   DuckDB SQL 批量执行
│   ├── validate_data.py          #   数据质量校验
│   └── benchmark_preprocessing.py #  Polars vs Pandas 性能基准
│
├── notebooks/                    # Jupyter 分析笔记本（5 份）
│   ├── 01_eda_and_visualization.ipynb
│   ├── 02_user_churn_prediction.ipynb
│   ├── 03_ab_test_analysis.ipynb
│   ├── 04_recommendation_system.ipynb
│   └── 05_cohort_and_ltv.ipynb
│
├── sql/                          # SQL 分析脚本（7 份）
│   ├── 01_database_setup.sql     #   Schema + 索引 + 视图
│   ├── 02_user_retention.sql     #   留存分析（D1/D3/D7）
│   ├── 03_conversion_funnel.sql  #   漏斗 + 路径分析
│   ├── 04_rfm_model.sql          #   RFM 分群
│   ├── 05_ab_test_framework.sql  #   A/B 测试数据准备
│   ├── 06_anomaly_detection.sql  #   异常检测（3σ 规则）
│   └── 07_product_analysis.sql   #   商品与品类分析
│
├── dbt/                          # dbt 数据模型 + 测试
│   ├── models/staging/
│   ├── models/intermediate/
│   └── models/marts/
│
├── pyspark/                      # PySpark 分布式计算（4 脚本）
├── dashboard/                    # Streamlit 交互看板
├── superset/                     # Apache Superset BI 配置
│   ├── superset_config.py        #   Superset 自定义配置
│   └── add_duckdb.py             #   DuckDB 数据源自动注册脚本
├── images/                       # 生成的图表
├── reports/                      # 分析报告
├── docs/                         # 架构决策记录（ADR）
├── docker-compose.superset.yml   # Superset Docker Compose 配置
├── Makefile                      # 工作流编排
└── requirements.txt
```

---

## BI 看板（Apache Superset）

除了 Streamlit 轻量看板，项目还集成了 **Apache Superset**（Docker）作为企业级 BI 探查工具：

```bash
# 启动 Superset（需 Docker）
docker compose -f docker-compose.superset.yml up -d

# 首次启动约需 1–2 分钟完成初始化
# 访问 http://localhost:8088
# 用户名: admin / 密码: admin
```

**已预配置内容：**
- DuckDB 数据源自动连接（`analytics.duckdb`）
- SQL Lab 可直接对 2,900 万行数据执行 Ad-hoc 查询
- Explore 界面支持拖拽式图表创建（日活趋势、转化漏斗、品类分布等）

**为什么同时保留 Streamlit + Superset？**

| 维度 | Streamlit | Apache Superset |
|------|-----------|-----------------|
| 定位 | 轻量自助看板 | 企业级 BI 探查 |
| 使用场景 | 固定指标监控 | Ad-hoc 分析、下钻、多维切片 |
| 开发方式 | Python 代码 | 零代码拖拽 + SQL |
| 受众 | 产品经理/运营 | 数据分析师/管理层 |

> 生产环境中，Streamlit 适合嵌入业务系统的固定看板，Superset 适合分析师自助探索。两者互补而非替代。

---

## 相关资源

- [`docs/ADR.md`](docs/ADR.md) — 架构决策记录：为什么选 DuckDB、Polars、dbt，以及扁平化目录结构的设计考量
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — 本地环境搭建、开发工作流、lint 规则与 commit 规范
- [`sql/README.md`](sql/README.md) — SQL 分析模块指南与数据库兼容性对照表

---

## 许可证

数据集遵循阿里云天池的使用条款。代码采用 MIT License，仅供学习交流使用。
