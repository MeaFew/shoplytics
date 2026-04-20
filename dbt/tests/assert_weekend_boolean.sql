-- 测试：周末标记 is_weekend 必须是 0 或 1（布尔约束）

SELECT *
FROM {{ ref('stg_user_behavior') }}
WHERE is_weekend NOT IN (0, 1)
