-- 测试：留存指标非负

SELECT new_users, retained_d1, retained_d3, retained_d7
FROM {{ ref('int_user_retention') }}
WHERE new_users < 0 OR retained_d1 < 0 OR retained_d3 < 0 OR retained_d7 < 0
