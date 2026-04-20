-- 测试：中间表和宽表中的指标非负

WITH all_metrics AS (
    SELECT dau, pv_count, buy_count, cart_count, fav_count
    FROM {{ ref('int_user_daily_metrics') }}
    UNION ALL
    SELECT new_users, retained_d1, retained_d3, retained_d7
    FROM {{ ref('int_user_retention') }}
    UNION ALL
    SELECT pv_users, fav_users, cart_users, buy_users
    FROM {{ ref('int_conversion_funnel') }}
)

SELECT *
FROM all_metrics
WHERE dau < 0 OR pv_count < 0 OR buy_count < 0 OR cart_count < 0 OR fav_count < 0
