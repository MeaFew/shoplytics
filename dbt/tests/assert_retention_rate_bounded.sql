-- 测试：留存率不能超过 100%（业务逻辑约束）
-- 留存用户数不可能超过 cohort 总用户数

SELECT *
FROM {{ ref('int_user_retention') }}
WHERE retention_d1_rate > 100
   OR retention_d3_rate > 100
   OR retention_d7_rate > 100
