-- ============================================================
-- 脚本名称: 06_anomaly_detection.sql
-- 用途: 计算每日核心指标并检测异常波动日期
-- 技术点: 窗口函数(移动平均) + 3σ原则
-- 运行方式: duckdb data/processed/analytics.duckdb < 06_anomaly_detection.sql
-- ============================================================
-- NOTE: 以下周末日期硬编码基于数据集时间窗口（2017-11-24 ~ 2017-12-03）。
-- 若更换数据集，请同步修改 config.py 中的 START_DATE / END_DATE，
-- 并替换本文件中所有硬编码日期。
-- ============================================================

-- --------------------------------------------------------
-- 第一部分: 每日核心指标计算
-- --------------------------------------------------------
WITH daily_metrics AS (
    SELECT 
        date,
        COUNT(DISTINCT user_id) AS dau,                    -- 日活跃用户
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_count,
        SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        -- 转化率
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate,
        -- 人均PV
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS pv_per_user,
        -- 购买用户占比
        ROUND(CAST(COUNT(DISTINCT CASE WHEN behavior_type = 'buy' THEN user_id END) AS REAL) * 100
              / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS buyer_pct
    FROM user_behavior
    GROUP BY date
)
SELECT 
    date,
    dau,
    pv_count,
    fav_count,
    cart_count,
    buy_count,
    conversion_rate,
    pv_per_user,
    buyer_pct
FROM daily_metrics
ORDER BY date;


-- --------------------------------------------------------
-- 第二部分: 3σ原则检测异常日期（基于全局统计）
-- --------------------------------------------------------
WITH daily_metrics AS (
    SELECT 
        date,
        COUNT(DISTINCT user_id) AS dau,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate
    FROM user_behavior
    GROUP BY date
),
-- 计算全局均值和标准差（用于3σ原则）
stats AS (
    SELECT 
        AVG(dau) AS avg_dau,
        -- 总体标准差计算: sqrt(avg(x^2) - avg(x)^2)
        SQRT(AVG(dau * dau) - AVG(dau) * AVG(dau)) AS std_dau,
        AVG(pv_count) AS avg_pv,
        SQRT(AVG(pv_count * pv_count) - AVG(pv_count) * AVG(pv_count)) AS std_pv,
        AVG(buy_count) AS avg_buy,
        SQRT(AVG(buy_count * buy_count) - AVG(buy_count) * AVG(buy_count)) AS std_buy,
        AVG(conversion_rate) AS avg_rate,
        SQRT(AVG(conversion_rate * conversion_rate) - AVG(conversion_rate) * AVG(conversion_rate)) AS std_rate
    FROM daily_metrics
)
SELECT 
    dm.date,
    dm.dau,
    dm.pv_count,
    dm.buy_count,
    dm.conversion_rate,
    -- 计算各指标与均值的偏差（Z-score）
    ROUND((dm.dau - s.avg_dau) / NULLIF(s.std_dau, 0), 2) AS dau_zscore,
    ROUND((dm.pv_count - s.avg_pv) / NULLIF(s.std_pv, 0), 2) AS pv_zscore,
    ROUND((dm.buy_count - s.avg_buy) / NULLIF(s.std_buy, 0), 2) AS buy_zscore,
    ROUND((dm.conversion_rate - s.avg_rate) / NULLIF(s.std_rate, 0), 2) AS rate_zscore,
    -- 标记异常: |z-score| > 2 为关注，> 3 为异常（9天数据样本小，放宽到2σ）
    CASE 
        WHEN ABS((dm.dau - s.avg_dau) / NULLIF(s.std_dau, 0)) > 2 THEN 'DAU异常'
        WHEN ABS((dm.pv_count - s.avg_pv) / NULLIF(s.std_pv, 0)) > 2 THEN 'PV异常'
        WHEN ABS((dm.buy_count - s.avg_buy) / NULLIF(s.std_buy, 0)) > 2 THEN '购买异常'
        WHEN ABS((dm.conversion_rate - s.avg_rate) / NULLIF(s.std_rate, 0)) > 2 THEN '转化率异常'
        ELSE '正常'
    END AS anomaly_flag
FROM daily_metrics dm
CROSS JOIN stats s
ORDER BY ABS((dm.conversion_rate - s.avg_rate) / NULLIF(s.std_rate, 0)) DESC;


-- --------------------------------------------------------
-- 第三部分: 移动平均法检测异常（更稳健的时间序列方法）
-- --------------------------------------------------------
WITH daily_metrics AS (
    SELECT 
        date,
        COUNT(DISTINCT user_id) AS dau,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate
    FROM user_behavior
    GROUP BY date
),
-- 使用窗口函数计算3日移动平均和移动标准差
moving_stats AS (
    SELECT 
        date,
        dau,
        pv_count,
        buy_count,
        conversion_rate,
        -- 前3日移动平均（不含当日）
        AVG(dau) OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS dau_ma3,
        -- 前3日移动标准差
        SQRT(AVG(dau * dau) OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) 
             - POWER(AVG(dau) OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING), 2)) AS dau_std3,
        -- 同理计算PV
        AVG(pv_count) OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS pv_ma3,
        SQRT(AVG(pv_count * pv_count) OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) 
             - POWER(AVG(pv_count) OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING), 2)) AS pv_std3,
        -- 同理计算转化率
        AVG(conversion_rate) OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS rate_ma3,
        SQRT(AVG(conversion_rate * conversion_rate) OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) 
             - POWER(AVG(conversion_rate) OVER (ORDER BY date ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING), 2)) AS rate_std3,
        -- 行号（前3日不足时标记）
        ROW_NUMBER() OVER (ORDER BY date) AS rn
    FROM daily_metrics
)
SELECT 
    date,
    dau,
    ROUND(dau_ma3, 2) AS dau_ma3,
    ROUND(pv_count, 0) AS pv_count,
    ROUND(pv_ma3, 2) AS pv_ma3,
    conversion_rate,
    ROUND(rate_ma3, 4) AS rate_ma3,
    -- 计算与移动平均的偏差（标准化）
    CASE 
        WHEN rn <= 3 THEN '样本不足'
        WHEN ABS(dau - dau_ma3) > 2 * NULLIF(dau_std3, 0) THEN 'DAU异常波动'
        WHEN ABS(pv_count - pv_ma3) > 2 * NULLIF(pv_std3, 0) THEN 'PV异常波动'
        WHEN ABS(conversion_rate - rate_ma3) > 2 * NULLIF(rate_std3, 0) THEN '转化率异常波动'
        ELSE '正常'
    END AS anomaly_flag,
    -- 偏差幅度
    CASE WHEN rn > 3 THEN ROUND((dau - dau_ma3) / NULLIF(dau_ma3, 0) * 100, 2) END AS dau_deviation_pct
FROM moving_stats
ORDER BY date;


-- --------------------------------------------------------
-- 第四部分: 异常日期深度分析（假设检测到异常，分析可能原因）
-- --------------------------------------------------------
WITH daily_metrics AS (
    SELECT 
        date,
        COUNT(DISTINCT user_id) AS dau,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate,
        COUNT(DISTINCT CASE WHEN behavior_type = 'buy' THEN user_id END) AS buyer_count
    FROM user_behavior
    GROUP BY date
),
-- 标记周末（2017-11-25是周六，11-26周日，12-02周六，12-03周日）
date_features AS (
    SELECT 
        date,
        dau,
        pv_count,
        buy_count,
        conversion_rate,
        buyer_count,
        CASE 
            WHEN date IN ('2017-11-25', '2017-11-26', '2017-12-02', '2017-12-03') THEN 1 
            ELSE 0 
        END AS is_weekend,
        -- 使用 LAG 对比前一日
        LAG(dau, 1) OVER (ORDER BY date) AS prev_dau,
        LAG(conversion_rate, 1) OVER (ORDER BY date) AS prev_rate
    FROM daily_metrics
)
SELECT 
    date,
    dau,
    ROUND((dau - prev_dau) * 100.0 / NULLIF(prev_dau, 0), 2) AS dau_mom_change,  -- 环比
    pv_count,
    buy_count,
    conversion_rate,
    buyer_count,
    is_weekend,
    CASE 
        WHEN is_weekend = 1 AND dau > prev_dau THEN '周末流量上涨'
        WHEN is_weekend = 1 AND dau < prev_dau THEN '周末流量下降（需关注）'
        WHEN is_weekend = 0 AND ABS((dau - prev_dau) * 100.0 / NULLIF(prev_dau, 0)) > 10 THEN '工作日大幅波动'
        ELSE '常规波动'
    END AS possible_reason
FROM date_features
ORDER BY date;


-- --------------------------------------------------------
-- 第五部分: 小时级异常检测（定位异常发生的具体时段）
-- --------------------------------------------------------
WITH hourly_metrics AS (
    SELECT 
        date,
        hour,
        COUNT(DISTINCT user_id) AS hourly_dau,
        SUM(CASE WHEN behavior_type = 'pv'  THEN 1 ELSE 0 END) AS pv_count,
        SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_count,
        ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
              / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate
    FROM user_behavior
    GROUP BY date, hour
),
-- 计算每个小时在所有日期中的均值和标准差
hourly_stats AS (
    SELECT 
        hour,
        AVG(hourly_dau) AS avg_dau,
        SQRT(AVG(hourly_dau * hourly_dau) - AVG(hourly_dau) * AVG(hourly_dau)) AS std_dau,
        AVG(pv_count) AS avg_pv,
        SQRT(AVG(pv_count * pv_count) - AVG(pv_count) * AVG(pv_count)) AS std_pv,
        AVG(conversion_rate) AS avg_rate,
        SQRT(AVG(conversion_rate * conversion_rate) - AVG(conversion_rate) * AVG(conversion_rate)) AS std_rate
    FROM hourly_metrics
    GROUP BY hour
)
SELECT 
    hm.date,
    hm.hour,
    hm.hourly_dau,
    ROUND(hs.avg_dau, 2) AS expected_dau,
    ROUND((hm.hourly_dau - hs.avg_dau) / NULLIF(hs.std_dau, 0), 2) AS dau_zscore,
    hm.conversion_rate,
    ROUND(hs.avg_rate, 4) AS expected_rate,
    -- 标记小时级异常
    CASE 
        WHEN ABS((hm.hourly_dau - hs.avg_dau) / NULLIF(hs.std_dau, 0)) > 2 THEN '时段DAU异常'
        WHEN ABS((hm.conversion_rate - hs.avg_rate) / NULLIF(hs.std_rate, 0)) > 2 THEN '时段转化率异常'
        ELSE '正常'
    END AS hourly_anomaly
FROM hourly_metrics hm
JOIN hourly_stats hs ON hm.hour = hs.hour
ORDER BY ABS((hm.hourly_dau - hs.avg_dau) / NULLIF(hs.std_dau, 0)) DESC
LIMIT 20;
