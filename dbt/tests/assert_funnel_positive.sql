-- 测试：漏斗各阶段用户数非负

SELECT pv_users, fav_users, cart_users, buy_users
FROM {{ ref('int_conversion_funnel') }}
WHERE pv_users < 0 OR fav_users < 0 OR cart_users < 0 OR buy_users < 0
