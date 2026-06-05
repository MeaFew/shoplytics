-- ============================================================
-- 脚本名称: 02_user_retention.sql
-- 用途: 计算每日新增用户及次日/3日/7日留存率
-- 技术点: 自连接 + 窗口函数
-- 运行方式: duckdb data/processed/analytics.duckdb < 02_user_retention.sql
-- ============================================================

-- --------------------------------------------------------
-- 第一部分: 计算每日新增用户数
-- --------------------------------------------------------
WITH user_first_active AS (
    -- 每个用户的首次活跃日期
    SELECT 
        user_id,
        MIN(date) AS first_date
    FROM user_behavior
    GROUP BY user_id
),
daily_new_users AS (
    -- 按日期汇总新增用户
    SELECT 
        first_date AS date,
        COUNT(DISTINCT user_id) AS new_users
    FROM user_first_active
    GROUP BY first_date
)
SELECT 
    date,
    new_users
FROM daily_new_users
ORDER BY date;


-- --------------------------------------------------------
-- 第二部分: 留存率计算（自连接实现）
-- --------------------------------------------------------
WITH user_first_active AS (
    SELECT 
        user_id,
        MIN(date) AS first_date
    FROM user_behavior
    GROUP BY user_id
),
-- 用户每日活跃标记（去重）
user_active_dates AS (
    SELECT DISTINCT user_id, date AS active_date
    FROM user_behavior
),
-- 新增用户在后续日期的活跃情况
retention_base AS (
    SELECT 
        f.user_id,
        f.first_date,
        a.active_date,
        -- 计算与首日的间隔天数
        DATE_DIFF('day', f.first_date, a.active_date) AS day_diff
    FROM user_first_active f
    LEFT JOIN user_active_dates a 
        ON f.user_id = a.user_id
       AND a.active_date >= f.first_date
)
SELECT 
    first_date AS date,
    COUNT(DISTINCT CASE WHEN day_diff = 0 THEN user_id END) AS new_users,
    -- 次日留存: 首日+1天仍活跃的用户占比
    COUNT(DISTINCT CASE WHEN day_diff = 1 THEN user_id END) AS retained_d1,
    ROUND(
        CAST(COUNT(DISTINCT CASE WHEN day_diff = 1 THEN user_id END) AS REAL) * 100
        / NULLIF(COUNT(DISTINCT CASE WHEN day_diff = 0 THEN user_id END), 0), 
        2
    ) AS retention_d1_pct,
    -- 3日留存: 首日+3天仍活跃的用户占比
    COUNT(DISTINCT CASE WHEN day_diff = 3 THEN user_id END) AS retained_d3,
    ROUND(
        CAST(COUNT(DISTINCT CASE WHEN day_diff = 3 THEN user_id END) AS REAL) * 100
        / NULLIF(COUNT(DISTINCT CASE WHEN day_diff = 0 THEN user_id END), 0), 
        2
    ) AS retention_d3_pct,
    -- 7日留存: 首日+7天仍活跃的用户占比
    COUNT(DISTINCT CASE WHEN day_diff = 7 THEN user_id END) AS retained_d7,
    ROUND(
        CAST(COUNT(DISTINCT CASE WHEN day_diff = 7 THEN user_id END) AS REAL) * 100
        / NULLIF(COUNT(DISTINCT CASE WHEN day_diff = 0 THEN user_id END), 0), 
        2
    ) AS retention_d7_pct
FROM retention_base
GROUP BY first_date
HAVING new_users > 0
ORDER BY first_date;


-- --------------------------------------------------------
-- 第三部分: 窗口函数版留存率（更灵活的留存矩阵）
-- --------------------------------------------------------
WITH user_first_active AS (
    SELECT 
        user_id,
        MIN(date) AS first_date
    FROM user_behavior
    GROUP BY user_id
),
user_active_dates AS (
    SELECT DISTINCT user_id, date AS active_date
    FROM user_behavior
),
-- 构建用户-日期活跃矩阵，并标记是否为新增日及后续活跃
retention_matrix AS (
    SELECT 
        f.user_id,
        f.first_date,
        a.active_date,
        DATE_DIFF('day', f.first_date, a.active_date) AS day_diff,
        -- 窗口函数: 在用户的所有活跃记录中，给每条记录打序号
        ROW_NUMBER() OVER (
            PARTITION BY f.user_id 
            ORDER BY a.active_date
        ) AS active_seq
    FROM user_first_active f
    LEFT JOIN user_active_dates a 
        ON f.user_id = a.user_id
       AND a.active_date >= f.first_date
)
SELECT 
    first_date AS cohort_date,
    COUNT(DISTINCT user_id) AS cohort_size,
    -- 使用窗口函数计算累计留存（展示高级SQL能力）
    SUM(CASE WHEN day_diff = 1 THEN 1 ELSE 0 END) AS d1_users,
    SUM(CASE WHEN day_diff = 2 THEN 1 ELSE 0 END) AS d2_users,
    SUM(CASE WHEN day_diff = 3 THEN 1 ELSE 0 END) AS d3_users,
    SUM(CASE WHEN day_diff = 4 THEN 1 ELSE 0 END) AS d4_users,
    SUM(CASE WHEN day_diff = 5 THEN 1 ELSE 0 END) AS d5_users,
    SUM(CASE WHEN day_diff = 6 THEN 1 ELSE 0 END) AS d6_users,
    SUM(CASE WHEN day_diff = 7 THEN 1 ELSE 0 END) AS d7_users,
    -- 留存率百分比
    ROUND(CAST(SUM(CASE WHEN day_diff = 1 THEN 1 ELSE 0 END) AS REAL) * 100 
          / COUNT(DISTINCT user_id), 2) AS d1_rate,
    ROUND(CAST(SUM(CASE WHEN day_diff = 3 THEN 1 ELSE 0 END) AS REAL) * 100 
          / COUNT(DISTINCT user_id), 2) AS d3_rate,
    ROUND(CAST(SUM(CASE WHEN day_diff = 7 THEN 1 ELSE 0 END) AS REAL) * 100 
          / COUNT(DISTINCT user_id), 2) AS d7_rate
FROM retention_matrix
GROUP BY first_date
HAVING cohort_size > 0
ORDER BY first_date;


-- --------------------------------------------------------
-- 第四部分: 留存率变化趋势（按日期展示）
-- --------------------------------------------------------
WITH user_first_active AS (
    SELECT user_id, MIN(date) AS first_date
    FROM user_behavior
    GROUP BY user_id
),
user_active_dates AS (
    SELECT DISTINCT user_id, date AS active_date
    FROM user_behavior
),
retention_trend AS (
    SELECT 
        f.first_date,
        DATE_DIFF('day', f.first_date, a.active_date) AS day_diff,
        COUNT(DISTINCT f.user_id) AS cohort_size,
        COUNT(DISTINCT CASE WHEN a.active_date IS NOT NULL THEN f.user_id END) AS retained_users
    FROM user_first_active f
    LEFT JOIN user_active_dates a 
        ON f.user_id = a.user_id
       AND a.active_date > f.first_date
    GROUP BY f.first_date, day_diff
)
SELECT 
    first_date,
    cohort_size,
    -- 使用 LAG 窗口函数获取前一天的留存率，计算留存率变化趋势
    ROUND(CAST(retained_users AS REAL) * 100 / cohort_size, 2) AS retention_rate,
    day_diff AS retention_day,
    LAG(ROUND(CAST(retained_users AS REAL) * 100 / cohort_size, 2), 1) 
        OVER (PARTITION BY day_diff ORDER BY first_date) AS prev_rate,
    ROUND(
        CAST(retained_users AS REAL) * 100 / cohort_size 
        - LAG(ROUND(CAST(retained_users AS REAL) * 100 / cohort_size, 2), 1) 
            OVER (PARTITION BY day_diff ORDER BY first_date),
        2
    ) AS rate_change
FROM retention_trend
WHERE day_diff IN (1, 3, 7)
ORDER BY day_diff, first_date;
