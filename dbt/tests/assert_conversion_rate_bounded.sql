-- 测试：日级购买转化率不能超过 100%（业务逻辑约束）
-- 购买次数不可能超过点击次数

SELECT *
FROM {{ ref('int_user_daily_metrics') }}
WHERE purchase_conversion_rate > 100
   OR cart_conversion_rate > 100
   OR fav_conversion_rate > 100
