-- ============================================================
-- 脚本名称: 04_rfm_model.sql
-- 用途: 基于Recency和Frequency的用户分层（RF分析）
-- 说明: 数据集无金额字段，简化为RF模型
-- 技术点: 窗口函数(NTILE) + CTE
-- 运行方式: duckdb data/processed/analytics.duckdb < 04_rfm_model.sql
-- ============================================================
-- NOTE: 以下日期硬编码基于数据集时间窗口（2017-11-24 ~ 2017-12-03）。
-- 若更换数据集，请同步修改 config.py 中的 END_DATE，
-- 并替换本文件中所有 '2017-12-03' 为新的截止日期。
-- ============================================================

-- --------------------------------------------------------
-- 第一部分: 计算每个用户的Recency和Frequency指标
-- --------------------------------------------------------
WITH user_stats AS (
    SELECT 
        user_id,
        -- Recency: 用户最近一次行为距数据集最后一天（2017-12-03）的天数
        -- 天数越小，用户越活跃
        DATE_DIFF('day', MAX(date), '2017-12-03') AS recency_days,
        -- Frequency: 用户总行为次数
        COUNT(*) AS total_actions,
        -- Frequency: 用户购买次数
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
        -- 用户首次行为日期
        MIN(date) AS first_date,
        -- 用户末次行为日期
        MAX(date) AS last_date,
        -- 行为覆盖天数
        COUNT(DISTINCT date) AS active_days
    FROM user_behavior
    GROUP BY user_id
),
-- --------------------------------------------------------
-- 第二部分: 使用NTILE窗口函数进行分箱（1-5分制）
-- --------------------------------------------------------
rf_scores AS (
    SELECT 
        user_id,
        recency_days,
        total_actions,
        buy_count,
        first_date,
        last_date,
        active_days,
        -- Recency评分: NTILE(5) 分箱后，天数越小分数越高（需反转）
        -- 注意: SQLite中NTILE按升序排列，因此recency_days小的在低位，需要反转
        (6 - NTILE(5) OVER (ORDER BY recency_days ASC)) AS r_score,
        -- Frequency评分: 行为次数越多分数越高
        NTILE(5) OVER (ORDER BY total_actions ASC) AS f_score_actions,
        -- 购买Frequency评分: 购买次数越多分数越高
        NTILE(5) OVER (ORDER BY buy_count ASC) AS f_score_buy
    FROM user_stats
)
SELECT 
    user_id,
    recency_days,
    total_actions,
    buy_count,
    active_days,
    r_score,
    f_score_actions,
    f_score_buy,
    -- 综合RF得分（简单相加，也可加权）
    r_score + f_score_actions AS rf_score,
    -- 用户分层标签
    CASE 
        WHEN r_score >= 4 AND f_score_actions >= 4 THEN '高价值用户'
        WHEN r_score >= 3 AND f_score_actions >= 3 THEN '活跃用户'
        WHEN r_score >= 3 AND f_score_actions <= 2 THEN '新用户/回流用户'
        WHEN r_score <= 2 AND f_score_actions >= 3 THEN '沉睡用户'
        WHEN r_score <= 2 AND f_score_actions <= 2 THEN '流失风险用户'
        ELSE '一般用户'
    END AS user_segment,
    -- 基于购买行为的细分
    CASE 
        WHEN buy_count > 0 THEN '已购买用户'
        ELSE '未购买用户'
    END AS purchase_status
FROM rf_scores
ORDER BY rf_score DESC, buy_count DESC
LIMIT 50;  -- 展示TOP50，实际分析时可去掉LIMIT


-- --------------------------------------------------------
-- 第三部分: 用户分层汇总统计
-- --------------------------------------------------------
WITH user_stats AS (
    SELECT 
        user_id,
        DATE_DIFF('day', MAX(date), '2017-12-03') AS recency_days,
        COUNT(*) AS total_actions,
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
        COUNT(DISTINCT date) AS active_days
    FROM user_behavior
    GROUP BY user_id
),
rf_scores AS (
    SELECT 
        user_id,
        recency_days,
        total_actions,
        buy_count,
        active_days,
        (6 - NTILE(5) OVER (ORDER BY recency_days ASC)) AS r_score,
        NTILE(5) OVER (ORDER BY total_actions ASC) AS f_score_actions
    FROM user_stats
),
segmented AS (
    SELECT 
        *,
        CASE 
            WHEN r_score >= 4 AND f_score_actions >= 4 THEN '高价值用户'
            WHEN r_score >= 3 AND f_score_actions >= 3 THEN '活跃用户'
            WHEN r_score >= 3 AND f_score_actions <= 2 THEN '新用户/回流用户'
            WHEN r_score <= 2 AND f_score_actions >= 3 THEN '沉睡用户'
            WHEN r_score <= 2 AND f_score_actions <= 2 THEN '流失风险用户'
            ELSE '一般用户'
        END AS user_segment
    FROM rf_scores
)
SELECT 
    user_segment,
    COUNT(*) AS user_count,
    ROUND(CAST(COUNT(*) AS REAL) * 100 / SUM(COUNT(*)) OVER (), 2) AS pct_of_total,
    ROUND(AVG(recency_days), 2) AS avg_recency_days,
    ROUND(AVG(total_actions), 2) AS avg_actions,
    ROUND(AVG(buy_count), 2) AS avg_buy_count,
    ROUND(AVG(active_days), 2) AS avg_active_days,
    SUM(buy_count) AS total_buy_count,
    -- 使用窗口函数计算该分层贡献的购买占比
    ROUND(CAST(SUM(buy_count) AS REAL) * 100 
          / SUM(SUM(buy_count)) OVER (), 2) AS buy_contribution_pct
FROM segmented
GROUP BY user_segment
ORDER BY user_count DESC;


-- --------------------------------------------------------
-- 第四部分: 用户价值分布（四分位分析）
-- --------------------------------------------------------
WITH user_stats AS (
    SELECT 
        user_id,
        DATE_DIFF('day', MAX(date), '2017-12-03') AS recency_days,
        COUNT(*) AS total_actions,
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_count
    FROM user_behavior
    GROUP BY user_id
)
SELECT 
    -- Recency分位数统计
    'Recency(天)' AS metric,
    MIN(recency_days) AS min_val,
    ROUND(AVG(recency_days), 2) AS avg_val,
    MAX(recency_days) AS max_val,
    -- 使用PERCENTILE近似（通过窗口函数排序取位置）
    (SELECT recency_days FROM (SELECT recency_days FROM user_stats ORDER BY recency_days LIMIT 1 OFFSET (SELECT COUNT(*) FROM user_stats) / 4)) AS q1,
    (SELECT recency_days FROM (SELECT recency_days FROM user_stats ORDER BY recency_days LIMIT 1 OFFSET (SELECT COUNT(*) FROM user_stats) / 2)) AS median,
    (SELECT recency_days FROM (SELECT recency_days FROM user_stats ORDER BY recency_days LIMIT 1 OFFSET (SELECT COUNT(*) FROM user_stats) * 3 / 4)) AS q3
FROM user_stats
UNION ALL
SELECT 
    'Frequency(行为次数)',
    MIN(total_actions),
    ROUND(AVG(total_actions), 2),
    MAX(total_actions),
    (SELECT total_actions FROM (SELECT total_actions FROM user_stats ORDER BY total_actions LIMIT 1 OFFSET (SELECT COUNT(*) FROM user_stats) / 4)),
    (SELECT total_actions FROM (SELECT total_actions FROM user_stats ORDER BY total_actions LIMIT 1 OFFSET (SELECT COUNT(*) FROM user_stats) / 2)),
    (SELECT total_actions FROM (SELECT total_actions FROM user_stats ORDER BY total_actions LIMIT 1 OFFSET (SELECT COUNT(*) FROM user_stats) * 3 / 4))
FROM user_stats
UNION ALL
SELECT 
    'Frequency(购买次数)',
    MIN(buy_count),
    ROUND(AVG(buy_count), 2),
    MAX(buy_count),
    (SELECT buy_count FROM (SELECT buy_count FROM user_stats ORDER BY buy_count LIMIT 1 OFFSET (SELECT COUNT(*) FROM user_stats) / 4)),
    (SELECT buy_count FROM (SELECT buy_count FROM user_stats ORDER BY buy_count LIMIT 1 OFFSET (SELECT COUNT(*) FROM user_stats) / 2)),
    (SELECT buy_count FROM (SELECT buy_count FROM user_stats ORDER BY buy_count LIMIT 1 OFFSET (SELECT COUNT(*) FROM user_stats) * 3 / 4))
FROM user_stats;


-- --------------------------------------------------------
-- 第五部分: 用户生命周期状态迁移（简化版）
-- --------------------------------------------------------
WITH user_daily AS (
    SELECT 
        user_id,
        date,
        COUNT(*) AS daily_actions,
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS daily_buy
    FROM user_behavior
    GROUP BY user_id, date
),
user_lifecycle AS (
    SELECT 
        user_id,
        date,
        daily_actions,
        daily_buy,
        -- 使用 LAG 获取用户前一天的活跃度
        LAG(daily_actions, 1) OVER (PARTITION BY user_id ORDER BY date) AS prev_day_actions,
        -- 使用 LEAD 获取用户后一天的活跃度
        LEAD(daily_actions, 1) OVER (PARTITION BY user_id ORDER BY date) AS next_day_actions,
        -- 用户在数据集中的活跃天数序号
        ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY date) AS active_seq
    FROM user_daily
)
SELECT 
    CASE 
        WHEN active_seq = 1 THEN '首次活跃'
        WHEN prev_day_actions IS NULL THEN '回流用户（间隔后活跃）'
        WHEN next_day_actions IS NULL THEN '当日末次活跃'
        ELSE '连续活跃'
    END AS lifecycle_status,
    COUNT(*) AS occurrence_count,
    ROUND(AVG(daily_actions), 2) AS avg_daily_actions,
    SUM(daily_buy) AS total_daily_buy
FROM user_lifecycle
GROUP BY lifecycle_status
ORDER BY occurrence_count DESC;
