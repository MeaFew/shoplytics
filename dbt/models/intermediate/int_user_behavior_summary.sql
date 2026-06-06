-- ============================================================
-- dbt intermediate: 用户行为汇总（全周期）
-- 用途: 汇总每个用户在整个观察期内的行为特征，用于流失预测和RFM
-- ============================================================

{{ config(materialized='table', schema='intermediate') }}

SELECT
    user_id,
    COUNT(DISTINCT event_date) AS active_days,
    SUM(total_actions) AS total_actions,
    SUM(pv_count) AS total_pv,
    SUM(fav_count) AS total_fav,
    SUM(cart_count) AS total_cart,
    SUM(buy_count) AS total_buy,
    SUM(is_purchase_day) AS purchase_days,
    SUM(is_cart_day) AS cart_days,
    SUM(unique_items) AS unique_items_touched,
    MIN(event_date) AS first_active_date,
    MAX(event_date) AS last_active_date,
    ROUND(CAST(SUM(buy_count) AS REAL) / NULLIF(SUM(pv_count), 0), 4) AS overall_conversion_rate
FROM {{ ref('int_user_daily_metrics') }}
GROUP BY user_id
