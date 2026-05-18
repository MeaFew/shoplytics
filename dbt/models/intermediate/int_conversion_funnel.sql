{{ config(
    materialized='table',
    description='转化漏斗中间表：从点击到购买的各环节转化数、转化率及不同路径分析'
) }}

-- 用户会话级行为序列（以user_id + item_id为一次交互）
WITH user_item_behavior AS (
    SELECT
        user_id,
        item_id,
        event_date,
        MAX(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END) AS has_pv,
        MAX(CASE WHEN behavior_type = 'fav' THEN 1 ELSE 0 END) AS has_fav,
        MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS has_buy
    FROM {{ ref('stg_user_behavior') }}
    GROUP BY user_id, item_id, event_date
),

-- 漏斗各环节计数
funnel_counts AS (
    SELECT
        event_date,
        COUNT(DISTINCT CASE WHEN has_pv = 1 THEN CONCAT(user_id, '_', item_id) END) AS pv_users,
        COUNT(DISTINCT CASE WHEN has_fav = 1 THEN CONCAT(user_id, '_', item_id) END) AS fav_users,
        COUNT(DISTINCT CASE WHEN has_cart = 1 THEN CONCAT(user_id, '_', item_id) END) AS cart_users,
        COUNT(DISTINCT CASE WHEN has_buy = 1 THEN CONCAT(user_id, '_', item_id) END) AS buy_users
    FROM user_item_behavior
    GROUP BY event_date
),

-- 路径分析：用户在同一天对同一商品的完整行为路径
user_paths AS (
    SELECT
        user_id,
        item_id,
        event_date,
        CASE
            WHEN has_buy = 1 AND has_cart = 1 AND has_fav = 1 THEN 'pv->fav->cart->buy'
            WHEN has_buy = 1 AND has_cart = 1 THEN 'pv->cart->buy'
            WHEN has_buy = 1 AND has_fav = 1 THEN 'pv->fav->buy'
            WHEN has_cart = 1 AND has_fav = 1 THEN 'pv->fav->cart'
            WHEN has_buy = 1 THEN 'pv->buy'
            WHEN has_cart = 1 THEN 'pv->cart'
            WHEN has_fav = 1 THEN 'pv->fav'
            ELSE 'pv_only'
        END AS conversion_path
    FROM user_item_behavior
),

-- 路径统计
path_stats AS (
    SELECT
        event_date,
        conversion_path,
        COUNT(*) AS path_count
    FROM user_paths
    GROUP BY event_date, conversion_path
)

SELECT
    fc.event_date,
    fc.pv_users,
    fc.fav_users,
    fc.cart_users,
    fc.buy_users,
    -- 各环节转化率（相对于上一环节）
    ROUND(
        CASE WHEN fc.pv_users > 0 THEN fc.fav_users * 100.0 / fc.pv_users ELSE 0 END, 2
    ) AS pv_to_fav_rate,
    ROUND(
        CASE WHEN fc.fav_users > 0 THEN fc.cart_users * 100.0 / fc.fav_users ELSE 0 END, 2
    ) AS fav_to_cart_rate,
    ROUND(
        CASE WHEN fc.cart_users > 0 THEN fc.buy_users * 100.0 / fc.cart_users ELSE 0 END, 2
    ) AS cart_to_buy_rate,
    -- 总体购买转化率（相对于PV）
    ROUND(
        CASE WHEN fc.pv_users > 0 THEN fc.buy_users * 100.0 / fc.pv_users ELSE 0 END, 2
    ) AS overall_buy_rate,
    -- 直接购买率（无加购/收藏直接购买）
    (
        SELECT path_count
        FROM path_stats ps
        WHERE ps.event_date = fc.event_date AND ps.conversion_path = 'pv->buy'
    ) AS direct_buy_count,
    -- 加购后购买率
    ROUND(
        CASE WHEN fc.cart_users > 0 THEN fc.buy_users * 100.0 / fc.cart_users ELSE 0 END, 2
    ) AS cart_buy_rate,
    CURRENT_TIMESTAMP AS _computed_at
FROM funnel_counts fc
ORDER BY fc.event_date
