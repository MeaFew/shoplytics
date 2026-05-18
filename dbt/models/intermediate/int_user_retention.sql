{{ config(
    materialized='table',
    description='留存分析中间表：每日新增用户及次日/3日/7日留存率'
) }}

-- 用户首次活跃日期（作为新增用户定义）
WITH user_first_active AS (
    SELECT
        user_id,
        MIN(event_date) AS first_active_date
    FROM {{ ref('stg_user_behavior') }}
    GROUP BY user_id
),

-- 每日活跃用户明细
daily_active AS (
    SELECT DISTINCT
        event_date,
        user_id
    FROM {{ ref('stg_user_behavior') }}
),

-- 每日新增用户数
daily_new_users AS (
    SELECT
        first_active_date AS event_date,
        COUNT(DISTINCT user_id) AS new_users
    FROM user_first_active
    GROUP BY first_active_date
),

-- 留存基表：新增用户后续活跃情况
retention_base AS (
    SELECT
        ufa.first_active_date,
        ufa.user_id,
        da.event_date,
        da.event_date - ufa.first_active_date AS day_diff
    FROM user_first_active ufa
    LEFT JOIN daily_active da
        ON ufa.user_id = da.user_id
        AND da.event_date >= ufa.first_active_date
),

-- 按日期和留存天数汇总
retention_summary AS (
    SELECT
        first_active_date,
        day_diff,
        COUNT(DISTINCT user_id) AS retained_users
    FROM retention_base
    GROUP BY first_active_date, day_diff
),

-- 计算留存率
retention_rates AS (
    SELECT
        dnu.event_date,
        dnu.new_users,
        -- 次日留存
        MAX(CASE WHEN rs.day_diff = 1 THEN rs.retained_users END) AS retained_d1,
        -- 3日留存
        MAX(CASE WHEN rs.day_diff = 3 THEN rs.retained_users END) AS retained_d3,
        -- 7日留存
        MAX(CASE WHEN rs.day_diff = 7 THEN rs.retained_users END) AS retained_d7
    FROM daily_new_users dnu
    LEFT JOIN retention_summary rs
        ON dnu.event_date = rs.first_active_date
    GROUP BY dnu.event_date, dnu.new_users
)

SELECT
    event_date,
    new_users,
    retained_d1,
    retained_d3,
    retained_d7,
    -- 次日留存率
    ROUND(
        CASE WHEN new_users > 0 THEN retained_d1 * 100.0 / new_users ELSE 0 END, 2
    ) AS retention_d1_rate,
    -- 3日留存率
    ROUND(
        CASE WHEN new_users > 0 THEN retained_d3 * 100.0 / new_users ELSE 0 END, 2
    ) AS retention_d3_rate,
    -- 7日留存率
    ROUND(
        CASE WHEN new_users > 0 THEN retained_d7 * 100.0 / new_users ELSE 0 END, 2
    ) AS retention_d7_rate,
    -- 窗口函数：留存率7日移动平均
    ROUND(AVG(
        CASE WHEN new_users > 0 THEN retained_d1 * 100.0 / new_users ELSE 0 END
    ) OVER (ORDER BY event_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS retention_d1_ma7
FROM retention_rates
ORDER BY event_date
