-- ============================================================
-- 脚本名称: 01_database_setup.sql
-- 用途: 创建数据库表结构、索引和视图
-- 数据集: 淘宝用户行为数据 (2017-11-25 至 2017-12-03)
-- 引擎: SQLite (开发环境) / Hive (生产等价)
--
-- 生产环境注意事项:
--   1. 添加分区字段: PARTITIONED BY (dt STRING)
--   2. 查询时必须加分区过滤: WHERE dt BETWEEN '2017-11-25' AND '2017-12-03'
--   3. 索引在生产中通常由 ORC/Parquet 文件格式 + 分区裁剪替代
--   4. 视图在生产中建议物化(materialized view)以减少重复计算
-- ============================================================

-- 1. 创建主表
DROP TABLE IF EXISTS user_behavior;

CREATE TABLE user_behavior (
    user_id       INTEGER,
    item_id       INTEGER,
    category_id   INTEGER,
    behavior_type TEXT,    -- 'pv'(点击), 'buy'(购买), 'cart'(加购), 'fav'(收藏)
    timestamp     INTEGER, -- Unix时间戳(秒)
    datetime      TEXT,    -- 日期时间字符串
    date          TEXT,    -- 日期
    hour          INTEGER, -- 小时(0-23)
    day_of_week   INTEGER, -- 星期(0=周一,6=周日)
    is_weekend    INTEGER, -- 是否周末(0/1)
    time_period   TEXT     -- 时间段
);

-- 2. 创建核心索引（加速常用查询条件）
-- 用户维度索引
CREATE INDEX IF NOT EXISTS idx_user_id 
    ON user_behavior(user_id);

-- 商品维度索引
CREATE INDEX IF NOT EXISTS idx_item_id 
    ON user_behavior(item_id);

-- 行为类型索引（漏斗分析高频使用）
CREATE INDEX IF NOT EXISTS idx_behavior_type 
    ON user_behavior(behavior_type);

-- 日期维度索引（时间序列分析）
CREATE INDEX IF NOT EXISTS idx_date 
    ON user_behavior(date);

-- 时间戳索引（留存、RFM等精确时间计算）
CREATE INDEX IF NOT EXISTS idx_timestamp 
    ON user_behavior(timestamp);

-- 复合索引：日期+行为（日报指标聚合）
CREATE INDEX IF NOT EXISTS idx_date_behavior 
    ON user_behavior(date, behavior_type);

-- 复合索引：用户+日期（留存分析）
CREATE INDEX IF NOT EXISTS idx_user_date 
    ON user_behavior(user_id, date);

-- 复合索引：用户+时间戳（RFM、用户路径）
CREATE INDEX IF NOT EXISTS idx_user_timestamp 
    ON user_behavior(user_id, timestamp);

-- 3. 创建分析视图

-- 视图1: 每日核心指标汇总（DAU、PV、购买量等）
DROP VIEW IF EXISTS v_daily_metrics;
CREATE VIEW v_daily_metrics AS
SELECT 
    date,
    COUNT(DISTINCT user_id) AS dau,                    -- 日活跃用户
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_count,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
    ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
          / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS buy_rate
FROM user_behavior
GROUP BY date;

-- 视图2: 用户每日行为汇总（留存、RFM基础）
DROP VIEW IF EXISTS v_user_daily_summary;
CREATE VIEW v_user_daily_summary AS
SELECT 
    user_id,
    date,
    COUNT(*) AS total_actions,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_count,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
    MAX(timestamp) AS last_timestamp
FROM user_behavior
GROUP BY user_id, date;

-- 视图3: 商品核心指标（商品分析基础）
DROP VIEW IF EXISTS v_item_metrics;
CREATE VIEW v_item_metrics AS
SELECT 
    item_id,
    category_id,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_count,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
    ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
          / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS conversion_rate
FROM user_behavior
GROUP BY item_id, category_id;

-- 视图4: 时段行为分布（时段分析基础）
DROP VIEW IF EXISTS v_hourly_distribution;
CREATE VIEW v_hourly_distribution AS
SELECT 
    hour,
    time_period,
    COUNT(*) AS total_actions,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_count,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_count,
    ROUND(CAST(SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS REAL)
          / NULLIF(SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END), 0), 4) AS buy_rate
FROM user_behavior
GROUP BY hour, time_period;

-- 视图5: 用户首次活跃日期（新增用户计算基础）
DROP VIEW IF EXISTS v_user_first_active;
CREATE VIEW v_user_first_active AS
SELECT 
    user_id,
    MIN(date) AS first_date,
    MIN(timestamp) AS first_timestamp
FROM user_behavior
GROUP BY user_id;

-- 完成提示
SELECT '数据库表结构、索引和视图创建完成' AS status;
