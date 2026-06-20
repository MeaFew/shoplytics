-- 测试：检测同一(用户,商品,日期)的异常高频行为。
-- 注意：此前的文件名为 assert_unique_user_id，但它并不检查唯一性
-- （同一用户同一天对同一商品允许多次浏览/加购/收藏），而是检测超过
-- 阈值的异常重复——已重命名为 assert_no_abnormal_repeat 以名副其实。
-- 真正的唯一性约束由 schema.yml 中的 unique 测试覆盖。

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
-- 同一用户对同一商品同一天行为超过100次视为异常（爬虫/刷量信号）
