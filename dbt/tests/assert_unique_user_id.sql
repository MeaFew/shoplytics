-- 测试：按天检查user_id + event_date的唯一性（同一用户同一天可有多条记录，但此处验证无异常重复）
-- 实际业务中：检查同一用户同一天对同一商品的行为是否唯一

WITH daily_user_item AS (
    SELECT
        user_id,
        item_id,
        event_date,
        COUNT(*) AS record_count
    FROM {{ ref('stg_user_behavior') }}
    GROUP BY user_id, item_id, event_date
)

SELECT *
FROM daily_user_item
WHERE record_count > 100
-- 如果同一用户对同一商品同一天行为超过100次，视为异常
