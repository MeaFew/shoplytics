-- 测试：每日指标中的核心计数非负

SELECT dau, pv_count, buy_count, cart_count, fav_count
FROM {{ ref('int_user_daily_metrics') }}
WHERE dau < 0 OR pv_count < 0 OR buy_count < 0 OR cart_count < 0 OR fav_count < 0
