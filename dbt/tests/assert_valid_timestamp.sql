-- 测试：时间戳范围检查，确保所有记录在项目定义的时间范围内

SELECT *
FROM {{ ref('stg_user_behavior') }}
WHERE event_date < DATE '{{ var("start_date") }}'
   OR event_date > DATE '{{ var("end_date") }}'
   OR event_timestamp < 1511462400  -- 2017-11-24 00:00:00 UTC
   OR event_timestamp > 1512863999  -- 2017-12-03 23:59:59 UTC
