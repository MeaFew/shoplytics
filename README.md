# E-commerce User Behavior Analytics

> A full-stack analytics pipeline on 29M real user behavior records from Alibaba Tianchi, covering data engineering (dbt), SQL analysis, statistical modeling, A/B testing, and interactive delivery (Streamlit).

---

## Data

- **Source**: [Alibaba Tianchi — Taobao User Behavior](https://tianchi.aliyun.com/dataset/649)
- **Scale**: 287,004 users · 2,584,151 items · 29,116,710 records · 10 days (2017-11-24 ~ 12-03)
- **Behaviors**: `pv` (page view) · `buy` · `cart` · `fav`

---

## Quick Start

```bash
git clone https://github.com/MeaFew/ecommerce-user-analytics.git
cd ecommerce-user-analytics
pip install -r requirements.txt

# Preprocess data (Polars: ~0.4s for 29M rows)
python python/scripts/01_data_preprocessing_polars.py \
  --input data/raw/UserBehavior.csv \
  --output data/processed/

# Run the full analysis pipeline (EDA + churn model + A/B test + cohort + LTV)
python python/scripts/run_analysis_pipeline.py

# Launch interactive dashboard
cd dashboard && streamlit run app.py
```

---

## Key Findings

| Metric | Value |
|--------|-------|
| Avg. DAU | 205,091 |
| PV → Purchase conversion | 2.24% |
| PV → Add-to-cart conversion | 6.21% |
| Cart → Purchase conversion | 36.04% |
| Avg. Day-1 retention | 73.54% |
| Items with zero conversion | 960,744 (37.2%) |

> Full analysis: [Business Insights Report](reports/business_insights_report.md)

---

## Architecture

```
ecommerce-user-analytics/
├── sql/                          # SQL analysis (7 scripts)
│   ├── 01_database_setup.sql     #   Schema + indexes + views
│   ├── 02_user_retention.sql     #   Retention (D1/D3/D7)
│   ├── 03_conversion_funnel.sql  #   Funnel + path analysis
│   ├── 04_rfm_model.sql          #   RFM segmentation
│   ├── 05_ab_test_framework.sql  #   A/B test data prep
│   ├── 06_anomaly_detection.sql  #   Outlier detection (3σ)
│   └── 07_product_analysis.sql   #   Product & category
│
├── python/
│   ├── notebooks/                # Jupyter notebooks (5)
│   │   ├── 01_eda_and_visualization.ipynb
│   │   ├── 02_user_churn_prediction.ipynb
│   │   ├── 03_ab_test_analysis.ipynb
│   │   ├── 04_recommendation_system.ipynb
│   │   └── 05_cohort_and_ltv.ipynb
│   └── scripts/                  # Python utilities
│       ├── 01_data_preprocessing.py
│       ├── 01_data_preprocessing_polars.py
│       ├── 02_data_analysis.py
│       ├── 03_daily_report_generator.py
│       └── run_analysis_pipeline.py
│
├── dbt/                          # dbt models + tests
│   ├── models/staging/
│   ├── models/intermediate/
│   └── models/marts/
│
├── pyspark/                      # PySpark (4 scripts)
├── dashboard/                    # Streamlit app
├── images/                       # Generated charts
└── reports/                      # Analysis reports
```

---

## Modules

| # | Module | Technique |
|---|--------|-----------|
| 1 | User Retention | Self-join + window functions (`ROW_NUMBER`, `LAG`) |
| 2 | Conversion Funnel | CTE + conditional aggregation + path classification |
| 3 | RFM Segmentation | `NTILE(5)` binning + lifecycle state migration |
| 4 | A/B Test Framework | Two-proportion Z-test · Chi-squared · Cohen's h · 95% CI |
| 5 | Churn Prediction | XGBoost vs Logistic Regression · 11-feature engineering · ROC |
| 6 | Recommendation | UserCF (cosine similarity) · ALS (PySpark MLlib) |
| 7 | Anomaly Detection | 3σ rule + moving average · Automated daily report with alerts |
| 8 | Cohort & LTV | Cohort retention heatmap · Behavior-weighted value estimation |
| 9 | Dashboard | Streamlit + Plotly · KPI cards · Funnel · RFM · Filters |
| 10 | Data Engineering | dbt staging → intermediate → marts · 7 data quality tests |

---

## Tech Stack

| Layer | Tools |
|-------|-------|
| Processing | **Polars** (Rust, 60x faster than Pandas) · Pandas · **PySpark** |
| SQL Engine | SQLite · **DuckDB** (zero-config OLAP) |
| Data Engineering | **dbt** (model versioning, testing, lineage) |
| Modeling | Scikit-learn · **XGBoost** · SciPy |
| Visualization | Matplotlib · Seaborn · **Plotly** |
| Delivery | **Streamlit** (interactive dashboard) · Jupyter |
| Version Control | Git · GitHub |

---

## Limitations

- **10-day window**: Cannot observe monthly/quarterly seasonality; retention beyond D7 is right-censored.
- **No monetary field**: GMV, ARPU, and CLV cannot be computed; RFM degrades to RF model.
- **No user attributes**: Demographics, device, and channel data are unavailable.
- **Simulated A/B test**: User-ID parity split is used as a proxy for random assignment.

---

## License

Dataset provided by Alibaba Tianchi under its usage terms. Code is for educational purposes.
