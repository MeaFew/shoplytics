{{ config(
    materialized='table',
    description='核心KPI宽表：整合所有日级指标，添加环比变化和3σ异常标记'
) }}

WITH daily_kpi_base AS (
    SELECT
        dm.event_date,
        dm.dau,
        dm.pv_count,
        dm.buy_count,
        dm.cart_count,
        dm.fav_count,
        dm.purchase_conversion_rate,
        dm.cart_conversion_rate,
        dm.fav_conversion_rate,
        dm.overall_conversion_rate,
        dm.avg_pv_per_user,
        dm.avg_buy_per_user,
        -- 留存指标
        COALESCE(r.retention_d1_rate, 0) AS retention_d1_rate,
        COALESCE(r.retention_d3_rate, 0) AS retention_d3_rate,
        COALESCE(r.retention_d7_rate, 0) AS retention_d7_rate,
        COALESCE(r.new_users, 0) AS new_users,
        -- 漏斗指标
        COALESCE(f.pv_users, dm.pv_count) AS funnel_pv,
        COALESCE(f.buy_users, dm.buy_count) AS funnel_buy,
        COALESCE(f.overall_buy_rate, dm.purchase_conversion_rate) AS funnel_buy_rate
    FROM {{ ref('int_user_daily_metrics') }} dm
    LEFT JOIN {{ ref('int_user_retention') }} r
        ON dm.event_date = r.event_date
    LEFT JOIN {{ ref('int_conversion_funnel') }} f
        ON dm.event_date = f.event_date
),

-- 计算各指标的均值和标准差（用于3σ异常检测）
stats AS (
    SELECT
        AVG(dau) AS avg_dau,
        STDDEV(dau) AS std_dau,
        AVG(purchase_conversion_rate) AS avg_conversion,
        STDDEV(purchase_conversion_rate) AS std_conversion,
        AVG(retention_d1_rate) AS avg_retention_d1,
        STDDEV(retention_d1_rate) AS std_retention_d1
    FROM daily_kpi_base
)

SELECT
    kpi.event_date,
    kpi.dau,
    kpi.pv_count,
    kpi.buy_count,
    kpi.cart_count,
    kpi.fav_count,
    kpi.purchase_conversion_rate,
    kpi.cart_conversion_rate,
    kpi.fav_conversion_rate,
    kpi.overall_conversion_rate,
    kpi.avg_pv_per_user,
    kpi.avg_buy_per_user,
    kpi.retention_d1_rate,
    kpi.retention_d3_rate,
    kpi.retention_d7_rate,
    kpi.new_users,
    kpi.funnel_pv,
    kpi.funnel_buy,
    kpi.funnel_buy_rate,
    -- 环比变化（与前一天比较）
    kpi.dau - LAG(kpi.dau) OVER (ORDER BY kpi.event_date) AS dau_change,
    ROUND(
        CASE WHEN LAG(kpi.dau) OVER (ORDER BY kpi.event_date) > 0
            THEN (kpi.dau - LAG(kpi.dau) OVER (ORDER BY kpi.event_date)) * 100.0
                / LAG(kpi.dau) OVER (ORDER BY kpi.event_date)
            ELSE 0
        END, 2
    ) AS dau_change_pct,
    kpi.purchase_conversion_rate - LAG(kpi.purchase_conversion_rate) OVER (ORDER BY kpi.event_date) AS conversion_change,
    -- 3σ异常标记
    CASE
        WHEN ABS(kpi.dau - s.avg_dau) > 3 * s.std_dau THEN 'abnormal'
        ELSE 'normal'
    END AS dau_anomaly_flag,
    CASE
        WHEN ABS(kpi.purchase_conversion_rate - s.avg_conversion) > 3 * s.std_conversion THEN 'abnormal'
        ELSE 'normal'
    END AS conversion_anomaly_flag,
    CASE
        WHEN ABS(kpi.retention_d1_rate - s.avg_retention_d1) > 3 * s.std_retention_d1 THEN 'abnormal'
        ELSE 'normal'
    END AS retention_anomaly_flag,
    -- 综合健康度评分（0-100）
    ROUND(
        LEAST(100, GREATEST(0,
            30 * (kpi.dau / NULLIF(MAX(kpi.dau) OVER (), 0))
            + 30 * (kpi.purchase_conversion_rate / NULLIF(MAX(kpi.purchase_conversion_rate) OVER (), 0))
            + 20 * (kpi.retention_d1_rate / NULLIF(MAX(kpi.retention_d1_rate) OVER (), 0))
            + 20 * (kpi.new_users / NULLIF(MAX(kpi.new_users) OVER (), 0))
        )), 0
    ) AS health_score,
    CURRENT_TIMESTAMP AS _computed_at
FROM daily_kpi_base kpi
CROSS JOIN stats s
ORDER BY kpi.event_date
