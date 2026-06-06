<p align="center">
  <h1 align="center">E-commerce User Behavior Analytics</h1>
  <p align="center">
    <b>A full-stack analytics pipeline on 29M real user behavior records from Taobao</b><br/>
    <sub>Data Engineering · SQL Analytics · Statistical Modeling · A/B Testing · Interactive Delivery</sub>
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
    <a href="./README.md">中文</a> | <b>English</b>
  </p>
</p>

---

## Highlights

- **Scale**: Cleans and engineers 29M rows in **~0.4s** on a single machine (Polars vectorized execution)
- **Engineering**: dbt data model layering (staging → intermediate → marts) + 7 data quality tests + GitHub Actions triple-gate (lint / sql-lint / docker-build)
- **End-to-end Methodology**: Covers the full user lifecycle — retention, conversion funnel, RFM segmentation, A/B testing, churn prediction, collaborative filtering recommendation
- **Production Mindset**: Every module includes a "Limitations → Production Path" analysis, not just toy examples

---

## Data

| Attribute | Value |
|-----------|-------|
| **Source** | Alibaba Tianchi — "Taobao User Behavior" Open Dataset |
| **Scale** | 287,004 users · 2,584,623 items · **29,128,402 records** |
| **Time Window** | Timestamps span 84 days (2017-04 ~ 2018-01); **99.96% of data concentrates in 2017-11-24 ~ 2017-12-03 (10 days)** |
| **Behaviors** | `pv` (page view) · `buy` · `cart` · `fav` |

> Second-level timestamps enable fine-grained behavioral sequence modeling; the 29M-row scale provides a solid testbed for benchmarking modern analytics tools like Polars / DuckDB.

### Dataset Statistics (Community Reference)

> This is an open dataset (not a competition). The metrics below are drawn from common community analyses and serve as reference for data scale and business benchmarks:

| Metric | Value | Description |
|--------|-------|-------------|
| Total Page Views (PV) | 3,431,900 | 10-day cumulative |
| Total Unique Visitors (UV) | 37,376 | Deduplicated users |
| Bounce Rate | **5.87%** | PV only, no other behavior |
| PV → Purchase Conversion | **2.2%** | Overall conversion |
| PV → Cart Add Conversion | **58.8%** | Product detail page effectiveness |
| Cart → Purchase Conversion | **38.9%** | Cart recovery potential |
| Repurchase Rate | **65.8%** | Users with 2+ purchases |

---

## Quick Start

```bash
git clone https://github.com/MeaFew/ecommerce-user-analytics.git
cd ecommerce-user-analytics

# Install dependencies and run the full pipeline
make setup
make all

# Launch the interactive dashboard
make dashboard

# Launch Apache Superset BI (requires Docker)
docker compose -f docker-compose.superset.yml up -d
# Open http://localhost:8088, login: admin / admin

# Local quality gates (mirrors CI)
make verify
```

---

## Key Metrics

| Metric | Value | Business Insight |
|--------|-------|------------------|
| Avg. DAU | 205,091 | Stable active user base during the 9-day core window |
| PV → Purchase Conversion | **2.24%** | Typical e-commerce level; optimization opportunity lies in homepage recommendation accuracy |
| PV → Cart Conversion | 6.21% | Product detail page design effectively drives add-to-cart behavior |
| Cart → Purchase Conversion | **36.04%** | Cart recovery (SMS / push) is a high-ROI optimization lever |
| Day-1 Retention | 73.54% | Healthy first-week retention for new users |
| Zero-Conversion Items | 37.2% (960,744) | Long-tail items suffer from traffic starvation; recommendation long-tail distribution needs optimization |

> Full business insights report: [reports/business_insights_report.md](reports/business_insights_report.md)

---

## Architecture

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
│  │ 7 scripts   │  │ staging →   │  │   ALS Matrix        │  │
│  │             │  │ intermediate│  │   Factorization     │  │
│  │             │  │ → marts     │  │   (Distributed)     │  │
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

## Ten Analytical Modules

| # | Module | Core Technique | Deliverable |
|---|--------|----------------|-------------|
| 1 | **User Retention** | Self-join + window functions (`ROW_NUMBER`, `LAG`) | D1/D3/D7 retention curves; identify churn inflection points |
| 2 | **Conversion Funnel** | CTE + conditional aggregation + path classification | Four-step funnel (PV → fav/cart → buy); locate the biggest leak |
| 3 | **RFM Segmentation** | `NTILE(5)` binning + lifecycle state migration | 8 user personas (Champions / Loyal / New / At Risk, etc.) |
| 4 | **A/B Test Framework** | Two-proportion Z-test · Chi-squared · Cohen's h · 95% CI | Full statistical pipeline: sample size → homogeneity check → effect size |
| 5 | **Churn Prediction** | XGBoost vs Logistic Regression · 11-feature engineering · ROC-AUC | AUC = 0.84; precisely identify high-risk users |
| 6 | **Recommendation** | UserCF (cosine similarity) · ALS (PySpark MLlib) | Side-by-side comparison of collaborative filtering + matrix factorization |
| 7 | **Anomaly Detection** | 3σ rule + moving average | Automated daily reports + anomaly behavior alerts |
| 8 | **Cohort & LTV** | Cohort retention heatmap · behavior-weighted value estimation | User cohort lifecycle value tracking |
| 9 | **Dashboard** | Streamlit + Plotly · KPI cards · funnel · RFM | Self-service analytics tool for product / ops teams |
| 10 | **Data Engineering** | dbt model layering · 7 data quality tests | Version-controlled analytics data pipeline |

---

## Tech Stack

| Layer | Tools | Rationale |
|-------|-------|-----------|
| Processing | **Polars** (Rust core) · Pandas · **PySpark** | Polars is ~60x faster than Pandas on 29M rows; PySpark for distributed ALS matrix factorization |
| SQL Engine | **DuckDB** | Zero-config columnar OLAP; sub-second aggregation of 29M rows on a single node |
| Data Engineering | **dbt** | Model versioning, lineage tracking, automated testing — elevates analytics SQL from scripts to engineered pipelines |
| Statistical Modeling | scikit-learn · **XGBoost** · SciPy · statsmodels | XGBoost handles high-dimensional sparse features; statsmodels provides classical statistical inference |
| Visualization | Matplotlib · Seaborn · **Plotly** | Plotly interactive charts embed directly into Streamlit |
| Delivery | **Streamlit** · **Apache Superset** · Jupyter | Streamlit for lightweight self-service dashboards; Superset (Docker) for enterprise BI exploration |
| Quality Assurance | pytest · **ruff** · sqlfluff · GitHub Actions | All-green CI = code style + SQL style + Docker build triple validation |

---

## Limitations & Production Path

| Limitation | Impact | Production Approach |
|------------|--------|---------------------|
| ~9-day effective window | Cannot observe monthly seasonality; D7+ retention is right-censored | Extend to ≥90 days of data; introduce Prophet / ARIMA forecasting |
| No monetary field | GMV, ARPU, CLV unavailable; RFM degrades to RF | Join with order / transaction table to complete the monetary dimension |
| No user attributes | Missing demographics, device, channel segmentation | Join with user profile table for multi-dimensional cohort analysis |
| Simulated A/B test | User-ID hash-based randomization as proxy | Hash randomization + SRM check + CUPED variance reduction |
| Single-node execution | DuckDB + local Parquet, no distributed query engine | Hive / Spark on partitioned Parquet + Airflow scheduling |

> The A/B test framework implements the full statistical pipeline (sample size calculation → homogeneity check → two-proportion Z-test → Cohen's h → 95% CI). Hash-based grouping is a **valid** randomization strategy when true experiment metadata is unavailable, and the statistical methodology transfers directly to production experiment platforms (e.g., internal AB platform or Optimizely).

---

## Project Structure

```
ecommerce-user-analytics/
├── scripts/                      # Python utility scripts
│   ├── preprocess.py             #   Polars ETL (~0.4s / 29M rows)
│   ├── pipeline.py               #   Full analysis pipeline orchestration
│   ├── run_sql.py                #   DuckDB SQL batch execution
│   ├── validate_data.py          #   Data quality validation
│   └── benchmark_preprocessing.py #  Polars vs Pandas performance benchmark
│
├── notebooks/                    # Jupyter analysis notebooks (5)
│   ├── 01_eda_and_visualization.ipynb
│   ├── 02_user_churn_prediction.ipynb
│   ├── 03_ab_test_analysis.ipynb
│   ├── 04_recommendation_system.ipynb
│   └── 05_cohort_and_ltv.ipynb
│
├── sql/                          # SQL analysis scripts (7)
│   ├── 01_database_setup.sql     #   Schema + indexes + views
│   ├── 02_user_retention.sql     #   Retention analysis (D1/D3/D7)
│   ├── 03_conversion_funnel.sql  #   Funnel + path analysis
│   ├── 04_rfm_model.sql          #   RFM segmentation
│   ├── 05_ab_test_framework.sql  #   A/B test data preparation
│   ├── 06_anomaly_detection.sql  #   Anomaly detection (3σ rule)
│   └── 07_product_analysis.sql   #   Product & category analysis
│
├── dbt/                          # dbt data models + tests
│   ├── models/staging/
│   ├── models/intermediate/
│   └── models/marts/
│
├── pyspark/                      # PySpark distributed computing (4 scripts)
├── dashboard/                    # Streamlit interactive dashboard
├── superset/                     # Apache Superset BI configuration
│   ├── superset_config.py        #   Custom Superset configuration
│   └── add_duckdb.py             #   DuckDB datasource auto-registration
├── images/                       # Generated charts
├── reports/                      # Analysis reports
├── docs/                         # Architecture Decision Records (ADR)
├── docker-compose.superset.yml   # Superset Docker Compose configuration
├── Makefile                      # Workflow orchestration
└── requirements.txt
```

---

## BI Dashboard (Apache Superset)

In addition to the lightweight Streamlit dashboard, the project integrates **Apache Superset** (Docker) as an enterprise-grade BI exploration tool:

```bash
# Start Superset (requires Docker)
docker compose -f docker-compose.superset.yml up -d

# First startup takes ~1–2 minutes for initialization
# Open http://localhost:8088
# Login: admin / Password: admin
```

**Pre-configured:**
- DuckDB datasource auto-connected (`analytics.duckdb`)
- SQL Lab for ad-hoc queries on 29M rows
- Explore interface for drag-and-drop chart creation (DAU trends, conversion funnels, category distributions)

**Why keep both Streamlit + Superset?**

| Dimension | Streamlit | Apache Superset |
|-----------|-----------|-----------------|
| Positioning | Lightweight self-service dashboard | Enterprise BI exploration |
| Use Case | Fixed KPI monitoring | Ad-hoc analysis, drill-down, multi-dimensional slicing |
| Development | Python code | Zero-code drag-and-drop + SQL |
| Audience | Product managers / Operations | Data analysts / Management |

> In production, Streamlit suits fixed dashboards embedded in business systems; Superset serves analyst self-service exploration. They complement rather than replace each other.

---

## Resources

- [`docs/ADR.md`](docs/ADR.md) — Architecture Decision Records: why DuckDB, Polars, dbt, and the flattened directory structure
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — Local setup, development workflow, lint rules, and commit conventions
- [`sql/README.md`](sql/README.md) — SQL analysis module guide and database compatibility reference

---

## License

Dataset provided by Alibaba Tianchi under its usage terms. Code is released under MIT License for educational purposes.
