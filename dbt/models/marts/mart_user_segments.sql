{{ config(
    materialized='table',
    description='用户分层宽表：RFM分层、用户标签和生命周期阶段'
) }}

-- 用户行为聚合（以整个数据周期为观察窗口）
WITH user_behavior_summary AS (
    SELECT
        user_id,
        MAX(event_date) AS last_active_date,
        MIN(event_date) AS first_active_date,
        COUNT(DISTINCT event_date) AS active_days,
        COUNT(CASE WHEN behavior_type = 'pv' THEN 1 END) AS pv_count,
        COUNT(CASE WHEN behavior_type = 'buy' THEN 1 END) AS buy_count,
        COUNT(CASE WHEN behavior_type = 'cart' THEN 1 END) AS cart_count,
        COUNT(CASE WHEN behavior_type = 'fav' THEN 1 END) AS fav_count,
        COUNT(DISTINCT item_id) AS unique_items,
        COUNT(DISTINCT category_id) AS unique_categories
    FROM {{ ref('stg_user_behavior') }}
    GROUP BY user_id
),

-- 计算RFM指标
rfm_base AS (
    SELECT
        user_id,
        -- Recency: 距离最后活跃日期的天数（数据截止日为2017-12-03）
        DATE_DIFF('day', last_active_date, DATE '2017-12-03') AS recency,
        -- Frequency: 活跃天数
        active_days AS frequency,
        -- Monetary: 购买次数（作为购买价值代理）
        buy_count AS monetary,
        first_active_date,
        last_active_date,
        pv_count,
        cart_count,
        fav_count,
        unique_items,
        unique_categories
    FROM user_behavior_summary
),

-- RFM分位数（1-5分）
rfm_scores AS (
    SELECT
        user_id,
        recency,
        frequency,
        monetary,
        first_active_date,
        last_active_date,
        pv_count,
        cart_count,
        fav_count,
        unique_items,
        unique_categories,
        -- Recency分数：越小越好（最近活跃分数高）
        NTILE(5) OVER (ORDER BY recency DESC) AS r_score,
        -- Frequency分数
        NTILE(5) OVER (ORDER BY frequency ASC) AS f_score,
        -- Monetary分数
        NTILE(5) OVER (ORDER BY monetary ASC) AS m_score
    FROM rfm_base
),

-- RFM综合评分和分层
user_segments AS (
    SELECT
        user_id,
        recency,
        frequency,
        monetary,
        first_active_date,
        last_active_date,
        pv_count,
        cart_count,
        fav_count,
        unique_items,
        unique_categories,
        r_score,
        f_score,
        m_score,
        -- RFM综合标签
        CASE
            WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN '重要价值用户'
            WHEN r_score >= 4 AND f_score >= 4 AND m_score < 4 THEN '重要发展用户'
            WHEN r_score >= 4 AND f_score < 4 AND m_score >= 4 THEN '重要保持用户'
            WHEN r_score >= 4 AND f_score < 4 AND m_score < 4 THEN '重要挽留用户'
            WHEN r_score < 4 AND f_score >= 4 AND m_score >= 4 THEN '一般价值用户'
            WHEN r_score < 4 AND f_score >= 4 AND m_score < 4 THEN '一般发展用户'
            WHEN r_score < 4 AND f_score < 4 AND m_score >= 4 THEN '一般保持用户'
            ELSE '流失风险用户'
        END AS rfm_segment,
        -- 用户价值等级
        CASE
            WHEN r_score + f_score + m_score >= 13 THEN '高价值'
            WHEN r_score + f_score + m_score >= 9 THEN '中价值'
            ELSE '低价值'
        END AS value_tier,
        -- 活跃度标签
        CASE
            WHEN recency = 0 THEN '今日活跃'
            WHEN recency <= 2 THEN '近期活跃'
            WHEN recency <= 5 THEN '一般活跃'
            ELSE '沉睡用户'
        END AS activity_label,
        -- 购买偏好标签
        CASE
            WHEN buy_count > 0 AND cart_count > 0 AND fav_count > 0 THEN '全链路用户'
            WHEN buy_count > 0 AND cart_count > 0 THEN '加购购买型'
            WHEN buy_count > 0 AND fav_count > 0 THEN '收藏购买型'
            WHEN buy_count > 0 THEN '直接购买型'
            WHEN cart_count > 0 OR fav_count > 0 THEN '意向用户'
            ELSE '浏览用户'
        END AS behavior_tag,
        -- 生命周期阶段
        CASE
            WHEN first_active_date >= DATE '2017-12-01' THEN '新用户'
            WHEN monetary > 0 AND frequency >= 5 THEN '成熟用户'
            WHEN monetary > 0 THEN '成长用户'
            WHEN frequency >= 3 THEN '活跃用户'
            ELSE '潜在用户'
        END AS lifecycle_stage,
        -- 购买转化率（个人）
        ROUND(
            CASE WHEN pv_count > 0 THEN buy_count * 100.0 / pv_count ELSE 0 END, 2
        ) AS personal_conversion_rate
    FROM rfm_scores
)

SELECT
    user_id,
    recency,
    frequency,
    monetary,
    first_active_date,
    last_active_date,
    pv_count,
    cart_count,
    fav_count,
    unique_items,
    unique_categories,
    r_score,
    f_score,
    m_score,
    rfm_segment,
    value_tier,
    activity_label,
    behavior_tag,
    lifecycle_stage,
    personal_conversion_rate,
    CURRENT_TIMESTAMP AS _computed_at
FROM user_segments
ORDER BY user_id
