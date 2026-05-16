-- ============================================================
-- 脚本名称: 07_product_analysis.sql
-- 用途: 商品与类目分析（热销、转化、长尾）
-- 技术点: 窗口函数(RANK) + CTE + 比率计算
-- 运行方式: sqlite3 user_behavior.db < 07_product_analysis.sql
-- ============================================================

-- --------------------------------------------------------
-- 第一部分: 热销商品TOP20（按购买量）
-- --------------------------------------------------------
WITH item_buy_stats AS (
    SELECT 
        item_id,
        category_id,
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
        SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END) AS pv_count,
        COUNT(DISTINCT CASE WHEN behavior_type = 'buy' THEN user_id END) AS buyer_count
    FROM user_behavior
    GROUP BY item_id, category_id
)
SELECT 
    item_id,
    category_id,
    buy_count,
    pv_count,
    buyer_count,
    ROUND(CAST(buy_count AS REAL) / NULLIF(pv_count, 0), 4) AS conversion_rate,
    -- 使用 RANK 窗口函数排名
    RANK() OVER (ORDER BY buy_count DESC) AS buy_rank,
    -- 使用 DENSE_RANK 窗口函数密集排名
    DENSE_RANK() OVER (ORDER BY buy_count DESC) AS buy_dense_rank
FROM item_buy_stats
ORDER BY buy_count DESC
LIMIT 20;


-- --------------------------------------------------------
-- 第二部分: 热销类目TOP10
-- --------------------------------------------------------
WITH category_stats AS (
    SELECT 
        category_id,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_count,
        SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        COUNT(DISTINCT item_id) AS item_count,           -- 类目下商品数
        COUNT(DISTINCT CASE WHEN behavior_type = 'buy' THEN user_id END) AS buyer_count
    FROM user_behavior
    GROUP BY category_id
)
SELECT 
    category_id,
    pv_count,
    fav_count,
    cart_count,
    buy_count,
    item_count,
    buyer_count,
    -- 类目整体转化率
    ROUND(CAST(buy_count AS REAL) / NULLIF(pv_count, 0), 4) AS category_conversion_rate,
    -- 人均购买量（购买次数/购买人数）
    ROUND(CAST(buy_count AS REAL) / NULLIF(buyer_count, 0), 2) AS avg_buy_per_buyer,
    -- 排名
    RANK() OVER (ORDER BY buy_count DESC) AS buy_rank,
    RANK() OVER (ORDER BY pv_count DESC) AS pv_rank,
    -- 综合排名：购买排名与流量排名的差异（识别高转化/低流量类目）
    RANK() OVER (ORDER BY pv_count DESC) - RANK() OVER (ORDER BY buy_count DESC) AS rank_diff
FROM category_stats
ORDER BY buy_count DESC
LIMIT 10;


-- --------------------------------------------------------
-- 第三部分: 商品点击→购买转化率TOP20
-- --------------------------------------------------------
WITH item_conversion AS (
    SELECT 
        item_id,
        category_id,
        SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
        COUNT(DISTINCT CASE WHEN behavior_type = 'buy' THEN user_id END) AS buyer_count
    FROM user_behavior
    GROUP BY item_id, category_id
    -- 过滤：至少有一定点击量才统计转化率（避免1次点击1次购买的极端值）
    HAVING SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END) >= 50
)
SELECT 
    item_id,
    category_id,
    pv_count,
    buy_count,
    buyer_count,
    ROUND(CAST(buy_count AS REAL) / pv_count, 4) AS conversion_rate,
    -- 排名
    RANK() OVER (ORDER BY ROUND(CAST(buy_count AS REAL) / pv_count, 4) DESC) AS conversion_rank,
    -- 购买量排名（对比转化排名，识别"高转化低销量"潜力商品）
    RANK() OVER (ORDER BY buy_count DESC) AS buy_rank
FROM item_conversion
ORDER BY conversion_rate DESC, pv_count DESC
LIMIT 20;


-- --------------------------------------------------------
-- 第四部分: 长尾商品分析（点击量高但购买量低的商品）
-- --------------------------------------------------------
WITH item_stats AS (
    SELECT 
        item_id,
        category_id,
        SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
        SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
        SUM(CASE WHEN behavior_type = 'fav' THEN 1 ELSE 0 END) AS fav_count
    FROM user_behavior
    GROUP BY item_id, category_id
),
-- 计算全局均值用于定义"高点击"和"低购买"
global_stats AS (
    SELECT 
        AVG(pv_count) AS avg_pv,
        AVG(buy_count) AS avg_buy,
        -- 使用窗口函数计算中位数近似值（通过排序取中间值）
        (SELECT pv_count FROM (SELECT pv_count FROM item_stats ORDER BY pv_count LIMIT 1 OFFSET (SELECT COUNT(*) FROM item_stats) / 2)) AS median_pv
    FROM item_stats
)
SELECT 
    s.item_id,
    s.category_id,
    s.pv_count,
    s.buy_count,
    s.cart_count,
    s.fav_count,
    ROUND(CAST(s.buy_count AS REAL) / NULLIF(s.pv_count, 0), 4) AS conversion_rate,
    -- 长尾标记: 点击量高于中位数，但转化率低于全局平均的1/10
    CASE 
        WHEN s.pv_count > g.median_pv 
             AND ROUND(CAST(s.buy_count AS REAL) / NULLIF(s.pv_count, 0), 4) < 0.001 
        THEN '高点击零转化'
        WHEN s.pv_count > g.median_pv 
             AND ROUND(CAST(s.buy_count AS REAL) / NULLIF(s.pv_count, 0), 4) < 0.005 
        THEN '高点击低转化'
        WHEN s.pv_count > g.avg_pv * 2 
             AND s.buy_count < g.avg_buy 
        THEN '流量浪费型'
        ELSE '正常'
    END AS long_tail_flag,
    -- 加购/收藏但未购买（用户有兴趣但未成交）
    CASE 
        WHEN s.cart_count + s.fav_count > 0 AND s.buy_count = 0 THEN '有意愿无转化'
        ELSE '已转化或无意愿'
    END AS intent_no_convert
FROM item_stats s
CROSS JOIN global_stats g
WHERE s.pv_count > g.median_pv  -- 只关注有一定流量的商品
ORDER BY s.pv_count DESC, conversion_rate ASC
LIMIT 30;


-- --------------------------------------------------------
-- 第五部分: 类目转化效率对比（识别优势/劣势类目）
-- --------------------------------------------------------
WITH category_conversion AS (
    SELECT 
        category_id,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_count,
        SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        COUNT(DISTINCT item_id) AS sku_count
    FROM user_behavior
    GROUP BY category_id
    HAVING SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END) >= 100  -- 过滤低流量类目
),
-- 计算全局平均转化率作为基准
global_avg AS (
    SELECT 
        SUM(buy_count) * 1.0 / SUM(pv_count) AS overall_conversion_rate
    FROM category_conversion
)
SELECT 
    c.category_id,
    c.sku_count,
    c.pv_count,
    c.buy_count,
    ROUND(CAST(c.buy_count AS REAL) / c.pv_count, 4) AS conversion_rate,
    g.overall_conversion_rate AS benchmark_rate,
    -- 与全局均值对比
    ROUND(CAST(c.buy_count AS REAL) / c.pv_count - g.overall_conversion_rate, 4) AS rate_diff,
    -- 相对提升/下降百分比
    ROUND((CAST(c.buy_count AS REAL) / c.pv_count - g.overall_conversion_rate) * 100 
          / g.overall_conversion_rate, 2) AS rate_diff_pct,
    -- 使用窗口函数分档
    CASE 
        WHEN CAST(c.buy_count AS REAL) / c.pv_count > g.overall_conversion_rate * 1.5 THEN '优秀类目'
        WHEN CAST(c.buy_count AS REAL) / c.pv_count > g.overall_conversion_rate THEN '良好类目'
        WHEN CAST(c.buy_count AS REAL) / c.pv_count > g.overall_conversion_rate * 0.5 THEN '一般类目'
        ELSE '低效类目'
    END AS category_grade,
    -- 类目内SKU平均流量
    ROUND(CAST(c.pv_count AS REAL) / c.sku_count, 2) AS avg_pv_per_sku,
    -- 排名
    RANK() OVER (ORDER BY CAST(c.buy_count AS REAL) / c.pv_count DESC) AS conversion_rank
FROM category_conversion c
CROSS JOIN global_avg g
ORDER BY conversion_rate DESC;


-- --------------------------------------------------------
-- 第六部分: 商品关联初步分析（同用户购买的商品组合）
-- --------------------------------------------------------
WITH user_buy_items AS (
    SELECT DISTINCT
        user_id,
        item_id,
        category_id
    FROM user_behavior
    WHERE behavior_type = 'buy'
),
-- 自连接找出被同一用户购买的商品对
item_pairs AS (
    SELECT 
        a.item_id AS item_a,
        b.item_id AS item_b,
        a.category_id AS cat_a,
        b.category_id AS cat_b
    FROM user_buy_items a
    JOIN user_buy_items b 
        ON a.user_id = b.user_id 
       AND a.item_id < b.item_id  -- 避免重复和自身配对
)
SELECT 
    item_a,
    item_b,
    cat_a,
    cat_b,
    COUNT(*) AS co_buy_count,  -- 共同购买次数
    -- 使用窗口函数计算该商品对在所有组合中的排名
    RANK() OVER (ORDER BY COUNT(*) DESC) AS pair_rank
FROM item_pairs
GROUP BY item_a, item_b
ORDER BY co_buy_count DESC
LIMIT 20;
