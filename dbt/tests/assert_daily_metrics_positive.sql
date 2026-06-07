-- 测试：每日指标中的核心计数非负
-- 引用 int_user_daily_metrics 实际存在的列

SELECT user_id, event_date, total_actions, pv_count, buy_count, cart_count, fav_count
FROM {{ ref('int_user_daily_metrics') }}
WHERE total_actions < 0 OR pv_count < 0 OR buy_count < 0 OR cart_count < 0 OR fav_count < 0
