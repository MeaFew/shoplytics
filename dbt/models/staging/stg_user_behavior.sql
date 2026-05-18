{{ config(
    materialized='view',
    description='清洗层：从原始CSV加载用户行为数据，进行基础类型转换和简单过滤'
) }}

-- 从原始CSV加载数据，进行基础清洗和类型转换
WITH raw_data AS (
    SELECT
        user_id::BIGINT AS user_id,
        item_id::BIGINT AS item_id,
        category_id::BIGINT AS category_id,
        behavior_type::VARCHAR AS behavior_type,
        timestamp::BIGINT AS event_timestamp,
        date::DATE AS event_date,
        hour::INTEGER AS event_hour,
        day_of_week::INTEGER AS day_of_week,
        is_weekend::INTEGER AS is_weekend,
        time_period::VARCHAR AS time_period
    FROM read_csv_auto('{{ var("data_path") }}', header=true, auto_detect=true)
)

SELECT
    user_id,
    item_id,
    category_id,
    behavior_type,
    event_timestamp,
    event_date,
    event_hour,
    day_of_week,
    is_weekend,
    time_period,
    -- 添加数据加载时间
    CURRENT_TIMESTAMP AS _loaded_at
FROM raw_data
WHERE
    -- 过滤无效记录
    user_id IS NOT NULL
    AND behavior_type IN ('pv', 'buy', 'cart', 'fav')
    AND event_date BETWEEN '{{ var("start_date") }}' AND '{{ var("end_date") }}'
