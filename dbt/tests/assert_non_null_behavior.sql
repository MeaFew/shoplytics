-- 测试：behavior_type字段非空且值在有效枚举范围内

SELECT *
FROM {{ ref('stg_user_behavior') }}
WHERE behavior_type IS NULL
   OR behavior_type NOT IN ('pv', 'buy', 'cart', 'fav')
