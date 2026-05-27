-- ============================================================
-- 脚本名称: 03_conversion_funnel.sql
-- 用途: 构建用户行为转化漏斗，分析各环节转化率
-- 技术点: CTE + 窗口函数 + 条件聚合
-- 运行方式: duckdb data/processed/analytics.duckdb < 03_conversion_funnel.sql
-- ============================================================

-- --------------------------------------------------------
-- 第一部分: 全量用户行为转化漏斗（pv → fav → cart → buy）
-- --------------------------------------------------------
WITH user_behavior_summary AS (
    -- 汇总每个用户各行为类型的发生次数
    SELECT 
        user_id,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_count,
        SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        -- 标记用户是否触达各环节（布尔化）
        MAX(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS has_pv,
        MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS has_fav,
        MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS has_buy
    FROM user_behavior
    GROUP BY user_id
),
funnel AS (
    SELECT 
        COUNT(*) AS total_users,
        SUM(has_pv)   AS pv_users,
        SUM(has_fav)  AS fav_users,
        SUM(has_cart) AS cart_users,
        SUM(has_buy)  AS buy_users
    FROM user_behavior_summary
)
SELECT 
    'pv'   AS stage,
    pv_users   AS user_count,
    100.0      AS conversion_rate,
    '总流量'   AS description
FROM funnel
UNION ALL
SELECT 
    'fav',
    fav_users,
    ROUND(CAST(fav_users AS REAL) * 100 / pv_users, 2),
    '点击→收藏转化率'
FROM funnel
UNION ALL
SELECT 
    'cart',
    cart_users,
    ROUND(CAST(cart_users AS REAL) * 100 / pv_users, 2),
    '点击→加购转化率'
FROM funnel
UNION ALL
SELECT 
    'buy',
    buy_users,
    ROUND(CAST(buy_users AS REAL) * 100 / pv_users, 2),
    '点击→购买转化率'
FROM funnel
ORDER BY user_count DESC;


-- --------------------------------------------------------
-- 第二部分: 相邻环节转化率（更精细的漏斗）
-- --------------------------------------------------------
WITH user_behavior_summary AS (
    SELECT 
        user_id,
        MAX(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS has_pv,
        MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS has_fav,
        MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS has_buy
    FROM user_behavior
    GROUP BY user_id
)
SELECT 
    'pv → fav'  AS funnel_step,
    SUM(CASE WHEN has_pv = 1 AND has_fav = 1 THEN 1 ELSE 0 END) AS converted_users,
    SUM(has_pv) AS from_users,
    ROUND(CAST(SUM(CASE WHEN has_pv = 1 AND has_fav = 1 THEN 1 ELSE 0 END) AS REAL) * 100
          / SUM(has_pv), 2) AS step_conversion_rate
FROM user_behavior_summary
UNION ALL
SELECT 
    'pv → cart',
    SUM(CASE WHEN has_pv = 1 AND has_cart = 1 THEN 1 ELSE 0 END),
    SUM(has_pv),
    ROUND(CAST(SUM(CASE WHEN has_pv = 1 AND has_cart = 1 THEN 1 ELSE 0 END) AS REAL) * 100
          / SUM(has_pv), 2)
FROM user_behavior_summary
UNION ALL
SELECT 
    'fav → buy',
    SUM(CASE WHEN has_fav = 1 AND has_buy = 1 THEN 1 ELSE 0 END),
    SUM(has_fav),
    ROUND(CAST(SUM(CASE WHEN has_fav = 1 AND has_buy = 1 THEN 1 ELSE 0 END) AS REAL) * 100
          / SUM(has_fav), 2)
FROM user_behavior_summary
UNION ALL
SELECT 
    'cart → buy',
    SUM(CASE WHEN has_cart = 1 AND has_buy = 1 THEN 1 ELSE 0 END),
    SUM(has_cart),
    ROUND(CAST(SUM(CASE WHEN has_cart = 1 AND has_buy = 1 THEN 1 ELSE 0 END) AS REAL) * 100
          / SUM(has_cart), 2)
FROM user_behavior_summary
UNION ALL
SELECT 
    'pv → buy(直接)',
    SUM(CASE WHEN has_pv = 1 AND has_buy = 1 AND has_fav = 0 AND has_cart = 0 THEN 1 ELSE 0 END),
    SUM(has_pv),
    ROUND(CAST(SUM(CASE WHEN has_pv = 1 AND has_buy = 1 AND has_fav = 0 AND has_cart = 0 THEN 1 ELSE 0 END) AS REAL) * 100
          / SUM(has_pv), 2)
FROM user_behavior_summary;


-- --------------------------------------------------------
-- 第三部分: 不同转化路径效率分析
-- --------------------------------------------------------
WITH user_paths AS (
    SELECT 
        user_id,
        MAX(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS has_pv,
        MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS has_fav,
        MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS has_buy
    FROM user_behavior
    GROUP BY user_id
),
path_classification AS (
    SELECT 
        user_id,
        CASE 
            WHEN has_buy = 0 THEN '未购买'
            WHEN has_fav = 1 AND has_cart = 1 THEN 'pv→fav+cart→buy'
            WHEN has_fav = 1 AND has_cart = 0 THEN 'pv→fav→buy'
            WHEN has_fav = 0 AND has_cart = 1 THEN 'pv→cart→buy'
            ELSE 'pv→buy(直接)'
        END AS conversion_path
    FROM user_paths
    WHERE has_pv = 1
)
SELECT 
    conversion_path,
    COUNT(*) AS user_count,
    ROUND(CAST(COUNT(*) AS REAL) * 100 
          / SUM(COUNT(*)) OVER (), 2) AS pct_of_total,
    -- 使用窗口函数计算每种路径的占比排名
    ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS path_rank
FROM path_classification
GROUP BY conversion_path
ORDER BY user_count DESC;


-- --------------------------------------------------------
-- 第四部分: 按日期分析转化漏斗变化
-- --------------------------------------------------------
WITH daily_user_behavior AS (
    SELECT 
        date,
        user_id,
        MAX(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS has_pv,
        MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS has_fav,
        MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS has_buy
    FROM user_behavior
    GROUP BY date, user_id
),
daily_funnel AS (
    SELECT 
        date,
        SUM(has_pv)   AS pv_users,
        SUM(has_fav)  AS fav_users,
        SUM(has_cart) AS cart_users,
        SUM(has_buy)  AS buy_users
    FROM daily_user_behavior
    GROUP BY date
)
SELECT 
    date,
    pv_users,
    fav_users,
    cart_users,
    buy_users,
    ROUND(CAST(fav_users AS REAL) * 100 / pv_users, 2) AS pv_to_fav_rate,
    ROUND(CAST(cart_users AS REAL) * 100 / pv_users, 2) AS pv_to_cart_rate,
    ROUND(CAST(buy_users AS REAL) * 100 / pv_users, 2) AS pv_to_buy_rate,
    -- 使用 LAG 窗口函数对比前一日转化率变化
    ROUND(CAST(buy_users AS REAL) * 100 / pv_users, 2)
        - LAG(ROUND(CAST(buy_users AS REAL) * 100 / pv_users, 2), 1) 
            OVER (ORDER BY date) AS buy_rate_change
FROM daily_funnel
ORDER BY date;


-- --------------------------------------------------------
-- 第五部分: 按时段分析转化漏斗
-- --------------------------------------------------------
WITH hourly_user_behavior AS (
    SELECT 
        time_period,
        user_id,
        MAX(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS has_pv,
        MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS has_fav,
        MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS has_buy
    FROM user_behavior
    GROUP BY time_period, user_id
),
hourly_funnel AS (
    SELECT 
        time_period,
        SUM(has_pv)   AS pv_users,
        SUM(has_fav)  AS fav_users,
        SUM(has_cart) AS cart_users,
        SUM(has_buy)  AS buy_users
    FROM hourly_user_behavior
    GROUP BY time_period
)
SELECT 
    time_period,
    pv_users,
    buy_users,
    ROUND(CAST(buy_users AS REAL) * 100 / pv_users, 2) AS conversion_rate,
    -- 使用 RANK 窗口函数找出转化率最高的时段
    RANK() OVER (ORDER BY ROUND(CAST(buy_users AS REAL) * 100 / pv_users, 2) DESC) AS conversion_rank
FROM hourly_funnel
ORDER BY conversion_rank;
