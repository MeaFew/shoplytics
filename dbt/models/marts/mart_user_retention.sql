-- ============================================================
-- dbt mart: 用户留存宽表
-- 用途: 计算 D1/D3/D7 留存率，支持 cohort 分析
-- ============================================================

{{ config(materialized='table', schema='marts', tags=['business_ready']) }}

WITH first_active AS (
    SELECT
        user_id,
        MIN(date) AS cohort_date
    FROM {{ ref('int_user_daily_metrics') }}
    GROUP BY user_id
),

retention AS (
    SELECT
        fa.cohort_date,
        dm.date AS activity_date,
        JULIANDAY(dm.date) - JULIANDAY(fa.cohort_date) AS day_diff,
        COUNT(DISTINCT dm.user_id) AS retained_users
    FROM first_active fa
    JOIN {{ ref('int_user_daily_metrics') }} dm
        ON fa.user_id = dm.user_id
    GROUP BY fa.cohort_date, dm.date
),

cohort_size AS (
    SELECT
        cohort_date,
        COUNT(*) AS cohort_users
    FROM first_active
    GROUP BY cohort_date
)

SELECT
    r.cohort_date,
    r.day_diff,
    r.retained_users,
    cs.cohort_users,
    ROUND(CAST(r.retained_users AS REAL) / cs.cohort_users, 4) AS retention_rate,
    CASE
        WHEN r.day_diff = 1 THEN 'D1'
        WHEN r.day_diff = 3 THEN 'D3'
        WHEN r.day_diff = 7 THEN 'D7'
        ELSE 'Other'
    END AS retention_label
FROM retention r
JOIN cohort_size cs ON r.cohort_date = cs.cohort_date
WHERE r.day_diff IN (1, 3, 7)
ORDER BY r.cohort_date, r.day_diff
