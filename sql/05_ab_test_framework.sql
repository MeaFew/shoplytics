-- ============================================================
-- 脚本名称: 05_ab_test_framework.sql
-- 用途: 模拟A/B测试场景，为统计检验提供SQL数据基础
-- 场景: 假设2017-12-01上线新功能，按user_id奇偶分组
-- 技术点: 条件聚合 + 窗口函数 + 统计量计算
-- 运行方式: sqlite3 user_behavior.db < 05_ab_test_framework.sql
-- ============================================================

-- --------------------------------------------------------
-- 第一部分: 实验分组定义与基础统计
-- --------------------------------------------------------
WITH experiment_setup AS (
    -- 定义实验日期和分组规则
    SELECT 
        '2017-12-01' AS experiment_date,  -- 假设新功能上线日期
        '2017-11-25' AS pre_period_start,   -- 实验前对照期
        '2017-11-30' AS pre_period_end,
        '2017-12-01' AS post_period_start,  -- 实验后观察期
        '2017-12-03' AS post_period_end
),
-- 用户分组：按user_id奇偶分为对照组/实验组
user_groups AS (
    SELECT DISTINCT
        user_id,
        CASE 
            WHEN user_id % 2 = 0 THEN 'control'    -- 偶数: 对照组
            ELSE 'treatment'                        -- 奇数: 实验组
        END AS group_label,
        user_id % 2 AS group_id
    FROM user_behavior
),
-- --------------------------------------------------------
-- 第二部分: 实验前基线指标（确保两组同质性）
-- --------------------------------------------------------
pre_metrics AS (
    SELECT 
        ug.group_label,
        ub.user_id,
        COUNT(*) AS total_actions,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_count,
        SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        -- 转化率: 购买行为 / 点击行为
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate
    FROM user_behavior ub
    JOIN user_groups ug ON ub.user_id = ug.user_id
    WHERE ub.date BETWEEN '2017-11-25' AND '2017-11-30'
    GROUP BY ug.group_label, ub.user_id
),
-- 实验前汇总
pre_summary AS (
    SELECT 
        group_label,
        COUNT(*) AS sample_size,
        ROUND(AVG(total_actions), 2) AS avg_actions,
        ROUND(AVG(pv_count), 2) AS avg_pv,
        ROUND(AVG(buy_count), 2) AS avg_buy,
        ROUND(AVG(conversion_rate), 4) AS avg_conversion_rate,
        -- 标准差: SQLite无内置stddev，使用数学公式计算
        ROUND(SQRT(AVG(conversion_rate * conversion_rate) - AVG(conversion_rate) * AVG(conversion_rate)), 4) AS std_conversion_rate,
        MIN(conversion_rate) AS min_conversion_rate,
        MAX(conversion_rate) AS max_conversion_rate
    FROM pre_metrics
    GROUP BY group_label
)
SELECT 
    '实验前基线' AS period,
    group_label,
    sample_size,
    avg_actions,
    avg_pv,
    avg_buy,
    avg_conversion_rate,
    std_conversion_rate,
    min_conversion_rate,
    max_conversion_rate
FROM pre_summary
ORDER BY group_label;


-- --------------------------------------------------------
-- 第三部分: 实验后指标对比
-- --------------------------------------------------------
WITH user_groups AS (
    SELECT DISTINCT
        user_id,
        CASE WHEN user_id % 2 = 0 THEN 'control' ELSE 'treatment' END AS group_label
    FROM user_behavior
),
post_metrics AS (
    SELECT 
        ug.group_label,
        ub.user_id,
        COUNT(*) AS total_actions,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate
    FROM user_behavior ub
    JOIN user_groups ug ON ub.user_id = ug.user_id
    WHERE ub.date BETWEEN '2017-12-01' AND '2017-12-03'
    GROUP BY ug.group_label, ub.user_id
),
post_summary AS (
    SELECT 
        group_label,
        COUNT(*) AS sample_size,
        ROUND(AVG(total_actions), 2) AS avg_actions,
        ROUND(AVG(pv_count), 2) AS avg_pv,
        ROUND(AVG(buy_count), 2) AS avg_buy,
        ROUND(AVG(conversion_rate), 4) AS avg_conversion_rate,
        ROUND(SQRT(AVG(conversion_rate * conversion_rate) - AVG(conversion_rate) * AVG(conversion_rate)), 4) AS std_conversion_rate,
        SUM(buy_count) AS total_buy,
        SUM(pv_count) AS total_pv
    FROM post_metrics
    GROUP BY group_label
)
SELECT 
    '实验后观察' AS period,
    group_label,
    sample_size,
    avg_actions,
    avg_pv,
    avg_buy,
    avg_conversion_rate,
    std_conversion_rate,
    total_buy,
    total_pv,
    ROUND(CAST(total_buy AS REAL) / total_pv, 4) AS overall_conversion_rate
FROM post_summary
ORDER BY group_label;


-- --------------------------------------------------------
-- 第四部分: 用户级明细数据（导出给Python做t检验/z检验）
-- --------------------------------------------------------
WITH user_groups AS (
    SELECT DISTINCT
        user_id,
        CASE WHEN user_id % 2 = 0 THEN 'control' ELSE 'treatment' END AS group_label
    FROM user_behavior
)
SELECT 
    ug.user_id,
    ug.group_label,
    -- 实验前指标
    COALESCE(pre.conversion_rate, 0) AS pre_conversion_rate,
    COALESCE(pre.buy_count, 0) AS pre_buy_count,
    COALESCE(pre.pv_count, 0) AS pre_pv_count,
    -- 实验后指标
    COALESCE(post.conversion_rate, 0) AS post_conversion_rate,
    COALESCE(post.buy_count, 0) AS post_buy_count,
    COALESCE(post.pv_count, 0) AS post_pv_count,
    -- 差值（用于配对检验或DID分析）
    COALESCE(post.conversion_rate, 0) - COALESCE(pre.conversion_rate, 0) AS conversion_diff
FROM user_groups ug
LEFT JOIN (
    SELECT 
        user_id,
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
        SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END) AS pv_count,
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate
    FROM user_behavior
    WHERE date BETWEEN '2017-11-25' AND '2017-11-30'
    GROUP BY user_id
) pre ON ug.user_id = pre.user_id
LEFT JOIN (
    SELECT 
        user_id,
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
        SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END) AS pv_count,
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate
    FROM user_behavior
    WHERE date BETWEEN '2017-12-01' AND '2017-12-03'
    GROUP BY user_id
) post ON ug.user_id = post.user_id
ORDER BY ug.group_label, ug.user_id
LIMIT 20;  -- 展示样例，实际导出时去掉LIMIT


-- --------------------------------------------------------
-- 第五部分: 分组统计量汇总（直接用于统计检验公式）
-- --------------------------------------------------------
WITH user_groups AS (
    SELECT DISTINCT
        user_id,
        CASE WHEN user_id % 2 = 0 THEN 'control' ELSE 'treatment' END AS group_label
    FROM user_behavior
),
post_user_metrics AS (
    SELECT 
        ug.group_label,
        ub.user_id,
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate
    FROM user_behavior ub
    JOIN user_groups ug ON ub.user_id = ug.user_id
    WHERE ub.date BETWEEN '2017-12-01' AND '2017-12-03'
    GROUP BY ug.group_label, ub.user_id
    HAVING SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END) > 0  -- 确保有PV行为
)
SELECT 
    group_label,
    COUNT(*) AS n,                                    -- 样本量
    ROUND(AVG(conversion_rate), 4) AS mean,           -- 均值
    -- 样本方差（无偏估计分母用n-1）
    ROUND(
        (COUNT(*) * SUM(conversion_rate * conversion_rate) - SUM(conversion_rate) * SUM(conversion_rate)) 
        / (COUNT(*) * (COUNT(*) - 1)),
        6
    ) AS variance,
    ROUND(SQRT(
        (COUNT(*) * SUM(conversion_rate * conversion_rate) - SUM(conversion_rate) * SUM(conversion_rate)) 
        / (COUNT(*) * (COUNT(*) - 1))
    ), 6) AS std_dev,                                 -- 标准差
    ROUND(MIN(conversion_rate), 4) AS min_rate,
    ROUND(MAX(conversion_rate), 4) AS max_rate
FROM post_user_metrics
GROUP BY group_label;
