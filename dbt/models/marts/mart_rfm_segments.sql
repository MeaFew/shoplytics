-- ============================================================
-- dbt mart: RFM 用户分层结果
-- 用途: 基于 NTILE(5) 的 RFM 评分，输出用户生命周期分层
-- ============================================================

{{ config(materialized='table', schema='marts', tags=['business_ready']) }}

WITH rfm_base AS (
    SELECT
        user_id,
        -- Recency: 距数据集最后一天的天数（天数越小越活跃）
        JULIANDAY('2017-12-03') - JULIANDAY(last_active_date) AS recency_days,
        -- Frequency: 活跃天数
        active_days AS frequency,
        -- Monetary proxy: 购买次数
        total_buy AS monetary
    FROM {{ ref('int_user_behavior_summary') }}
),

rfm_scored AS (
    SELECT
        user_id,
        recency_days,
        frequency,
        monetary,
        NTILE(5) OVER (ORDER BY recency_days ASC) AS r_score,      -- Recency 越小越好
        NTILE(5) OVER (ORDER BY frequency DESC) AS f_score,       -- Frequency 越大越好
        NTILE(5) OVER (ORDER BY monetary DESC) AS m_score         -- Monetary 越大越好
    FROM rfm_base
),

rfm_segmented AS (
    SELECT
        *,
        r_score * 100 + f_score * 10 + m_score AS rfm_score,
        CASE
            WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN '高价值用户'
            WHEN r_score >= 3 AND f_score >= 3 THEN '潜力用户'
            WHEN r_score >= 4 AND f_score <= 2 THEN '新用户'
            WHEN r_score <= 2 AND f_score >= 3 THEN '流失预警'
            WHEN r_score <= 2 AND f_score <= 2 THEN '沉睡用户'
            ELSE '一般用户'
        END AS segment_label
    FROM rfm_scored
)

SELECT * FROM rfm_segmented
ORDER BY rfm_score DESC
