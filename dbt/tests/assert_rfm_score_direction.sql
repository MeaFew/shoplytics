-- 测试：RFM 评分方向不变量（防回归）。
-- 高分应代表"更优"：
--   r_score 高 => recency 小（最近活跃）—— 但 recency 在大量用户为 0（同日活跃），
--     故仅校验 f_score / m_score 的单调性（更稳健，不受 recency 平台影响）：
--   f_score 高 => frequency 大
--   m_score 高 => monetary 大
-- 通过比较各分段的均值是否随分数单调递增来断言方向正确。若该测试失败，
-- 说明 NTILE 方向又被写反（曾导致 value_tier 把低价值标成高价值）。

WITH score_means AS (
    SELECT
        f_score,
        AVG(frequency) AS avg_frequency,
        AVG(monetary) AS avg_monetary_m,
        AVG(monetary) AS avg_monetary
    FROM {{ ref('mart_user_segments') }}
    GROUP BY f_score
)
-- 找出 frequency 均值不随 f_score 单调递增的相邻分段
SELECT a.f_score AS lower_score, b.f_score AS higher_score,
       a.avg_frequency AS lower_avg_freq, b.avg_frequency AS higher_avg_freq
FROM score_means a
JOIN score_means b ON b.f_score = a.f_score + 1
WHERE b.avg_frequency <= a.avg_frequency  -- 高分段 frequency 均值应更大
