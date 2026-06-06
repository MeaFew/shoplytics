-- ============================================================
-- dbt intermediate: 用户日级聚合指标
-- 用途: 将原始行为数据按用户+日期聚合，为下游留存、LTV模型提供输入
-- ============================================================

{{ config(materialized='table', schema='intermediate') }}

WITH daily_behavior AS (
    SELECT
        user_id,
        event_date,
        COUNT(*) AS total_actions,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_count,
        SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        COUNT(DISTINCT item_id) AS unique_items,
        COUNT(DISTINCT category_id) AS unique_categories,
        MIN(event_timestamp) AS first_action_ts,
        MAX(event_timestamp) AS last_action_ts
    FROM {{ ref('stg_user_behavior') }}
    GROUP BY user_id, event_date
)

SELECT
    user_id,
    event_date,
    total_actions,
    pv_count,
    fav_count,
    cart_count,
    buy_count,
    unique_items,
    unique_categories,
    first_action_ts,
    last_action_ts,
    -- 购买转化率（当日）
    CASE WHEN pv_count > 0 THEN ROUND(CAST(buy_count AS REAL) / pv_count, 4) ELSE 0 END AS conversion_rate,
    -- 是否活跃日（有购买行为）
    CASE WHEN buy_count > 0 THEN 1 ELSE 0 END AS is_purchase_day,
    -- 是否加购日
    CASE WHEN cart_count > 0 THEN 1 ELSE 0 END AS is_cart_day
FROM daily_behavior
