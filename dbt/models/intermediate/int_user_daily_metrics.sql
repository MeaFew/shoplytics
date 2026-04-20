{{ config(
    materialized='table',
    description='日级指标中间表：每日DAU、PV、购买量、加购量、收藏量及转化率'
) }}

WITH daily_behavior AS (
    SELECT
        event_date,
        user_id,
        behavior_type,
        COUNT(*) AS behavior_count
    FROM {{ ref('stg_user_behavior') }}
    GROUP BY event_date, user_id, behavior_type
),

-- 每日各行为指标汇总
daily_metrics AS (
    SELECT
        event_date,
        COUNT(DISTINCT user_id) AS dau,
        SUM(CASE WHEN behavior_type = 'pv' THEN behavior_count END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'buy' THEN behavior_count END) AS buy_count,
        SUM(CASE WHEN behavior_type = 'cart' THEN behavior_count END) AS cart_count,
        SUM(CASE WHEN behavior_type = 'fav' THEN behavior_count END) AS fav_count
    FROM daily_behavior
    GROUP BY event_date
),

-- 计算转化率
daily_conversion AS (
    SELECT
        event_date,
        dau,
        pv_count,
        buy_count,
        cart_count,
        fav_count,
        -- 购买转化率 = 购买次数 / 点击次数
        ROUND(
            CASE WHEN pv_count > 0 THEN buy_count * 100.0 / pv_count ELSE 0 END, 2
        ) AS purchase_conversion_rate,
        -- 加购转化率 = 加购次数 / 点击次数
        ROUND(
            CASE WHEN pv_count > 0 THEN cart_count * 100.0 / pv_count ELSE 0 END, 2
        ) AS cart_conversion_rate,
        -- 收藏转化率 = 收藏次数 / 点击次数
        ROUND(
            CASE WHEN pv_count > 0 THEN fav_count * 100.0 / pv_count ELSE 0 END, 2
        ) AS fav_conversion_rate,
        -- 综合转化率 = (购买+加购+收藏) / 点击次数
        ROUND(
            CASE WHEN pv_count > 0 THEN (buy_count + cart_count + fav_count) * 100.0 / pv_count ELSE 0 END, 2
        ) AS overall_conversion_rate
    FROM daily_metrics
)

SELECT
    event_date,
    dau,
    pv_count,
    buy_count,
    cart_count,
    fav_count,
    purchase_conversion_rate,
    cart_conversion_rate,
    fav_conversion_rate,
    overall_conversion_rate,
    -- 人均PV
    ROUND(CASE WHEN dau > 0 THEN pv_count * 1.0 / dau ELSE 0 END, 2) AS avg_pv_per_user,
    -- 人均购买
    ROUND(CASE WHEN dau > 0 THEN buy_count * 1.0 / dau ELSE 0 END, 2) AS avg_buy_per_user
FROM daily_conversion
ORDER BY event_date
