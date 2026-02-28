# SQL 分析模块使用说明

## 模块概述

本目录包含拼多多数据分析师求职项目的 **7个核心SQL分析脚本** 和 **1个数据库初始化脚本**，基于阿里云天池淘宝用户行为数据集（2017-11-25 至 2017-12-03，共9天），使用 **SQLite** 方言编写，兼容 MySQL 语法习惯。

---

## 文件清单

| 序号 | 文件名 | 用途 | 核心技术 |
|------|--------|------|----------|
| 1 | `01_database_setup.sql` | 创建表结构、索引、视图 | DDL + 复合索引设计 |
| 2 | `02_user_retention.sql` | 新增用户与次日/3日/7日留存率 | 自连接 + 窗口函数(ROW_NUMBER, LAG) |
| 3 | `03_conversion_funnel.sql` | 用户行为转化漏斗与路径分析 | CTE + 条件聚合 + RANK |
| 4 | `04_rfm_model.sql` | 用户RF分层（Recency + Frequency） | NTILE分箱 + 用户生命周期(LAG/LEAD) |
| 5 | `05_ab_test_framework.sql` | A/B测试分组与统计量计算 | 方差/标准差SQL实现 + 实验设计 |
| 6 | `06_anomaly_detection.sql` | 核心指标监控与异常检测 | 3σ原则 + 移动平均窗口函数 |
| 7 | `07_product_analysis.sql` | 热销/转化/长尾商品分析 | RANK/DENSE_RANK + 关联规则初步 |
| 8 | `README.md` | 本说明文档 | — |

---

## 环境准备

### 1. 创建数据库并导入数据

```bash
# 进入SQL目录
cd E:\NewWorkProject\PDD\pdd-data-analyst-project\sql\

# 创建数据库（如尚未创建）
sqlite3 user_behavior.db < 01_database_setup.sql

# 导入CSV数据（假设数据文件为 user_behavior.csv）
sqlite3 user_behavior.db <<EOF
.mode csv
.import ../data/user_behavior.csv user_behavior
EOF
```

> **注意**: 如果数据已通过其他方式导入，可直接运行 `01_database_setup.sql` 创建索引和视图。

### 2. 运行分析脚本

```bash
# 运行单个脚本
sqlite3 user_behavior.db < 02_user_retention.sql

# 将结果输出到文件
sqlite3 user_behavior.db < 03_conversion_funnel.sql > ../reports/conversion_funnel.txt

# 以CSV格式输出（便于Python/Pandas读取）
sqlite3 -header -csv user_behavior.db < 04_rfm_model.sql > ../reports/rfm_model.csv
```

---

## 各脚本详解

### 01_database_setup.sql

**用途**: 搭建数据分析基础设施。

**核心设计**:
- **主表**: `user_behavior` 存储全部用户行为记录
- **索引策略**: 覆盖高频查询维度（user_id, item_id, behavior_type, date, timestamp），并增加复合索引加速日报和留存查询
- **视图层**:
  - `v_daily_metrics`: 每日DAU、PV、购买量、转化率
  - `v_user_daily_summary`: 用户-日期粒度行为汇总
  - `v_item_metrics`: 商品核心指标
  - `v_hourly_distribution`: 时段行为分布
  - `v_user_first_active`: 用户首次活跃日期（新增用户计算基础）

**运行时机**: 数据导入后 **首先运行**。

---

### 02_user_retention.sql

**用途**: 计算用户留存率，评估产品粘性。

**关键查询**:
1. **每日新增用户**: 通过 `MIN(date)` 找到用户首日，按日期汇总
2. **留存率（自连接版）**: 将用户首日与后续活跃日期关联，计算 `day_diff = 1/3/7` 的留存比例
3. **留存矩阵（窗口函数版）**: 使用 `ROW_NUMBER()` 标记用户活跃序列，生成 cohort 留存表
4. **留存趋势**: 使用 `LAG()` 对比前一日留存率，计算变化幅度

**输出指标**:
- `new_users`: 当日新增用户数
- `retention_d1_pct`: 次日留存率(%)
- `retention_d3_pct`: 3日留存率(%)
- `retention_d7_pct`: 7日留存率(%)

---

### 03_conversion_funnel.sql

**用途**: 构建用户行为转化漏斗，识别转化瓶颈。

**关键查询**:
1. **全量漏斗**: 统计有过 `pv/fav/cart/buy` 行为的独立用户数，计算各环节占比
2. **相邻环节转化**: `pv→fav`, `pv→cart`, `fav→buy`, `cart→buy` 的精细转化率
3. **转化路径分析**: 将用户分类为 `直接购买`、`收藏后购买`、`加购后购买`、`收藏+加购后购买`、`未购买`
4. **日期/时段漏斗**: 使用 `LAG()` 对比前一日转化率变化；使用 `RANK()` 找出转化率最高的时段

**业务洞察**:
- 哪一步流失最严重？
- 用户更倾向于收藏还是加购？
- 哪个时段的转化效率最高？

---

### 04_rfm_model.sql

**用途**: 用户价值分层（因无金额字段，简化为 **RF模型**）。

**关键定义**:
- **Recency (R)**: 用户最近一次行为距数据集最后一天（2017-12-03）的天数，天数越小越活跃
- **Frequency (F)**: 用户总行为次数 + 购买次数

**技术实现**:
- 使用 `NTILE(5)` 窗口函数将用户按 Recency 和 Frequency 分为5档
- R_score 反转（`6 - NTILE(...)`），确保最近活跃的用户得高分
- 综合 `rf_score` 将用户分为6层:
  - `高价值用户` (R≥4, F≥4)
  - `活跃用户` (R≥3, F≥3)
  - `新用户/回流用户` (R≥3, F≤2)
  - `沉睡用户` (R≤2, F≥3)
  - `流失风险用户` (R≤2, F≤2)
  - `一般用户`

**附加分析**:
- 用户生命周期状态迁移（首次活跃 / 连续活跃 / 回流 / 末次活跃）
- 各分层贡献的购买占比

---

### 05_ab_test_framework.sql

**用途**: 模拟A/B测试场景，为统计检验准备数据。

**实验设计**:
- **假设**: 2017-12-01 上线新功能
- **分组**: `user_id % 2 = 0` → 对照组(control)，`user_id % 2 = 1` → 实验组(treatment)
- **观察期**: 2017-12-01 至 2017-12-03
- **对照期**: 2017-11-25 至 2017-11-30（用于检验分组同质性）

**输出内容**:
1. **实验前基线**: 两组的均值、转化率、标准差，确保分组无偏
2. **实验后对比**: 两组在观察期的核心指标差异
3. **用户级明细**: 每个用户的 `pre_conversion_rate`, `post_conversion_rate`, `conversion_diff`（可直接导出给Python做 t检验 / DID分析）
4. **统计量汇总**: 样本量 `n`、均值 `mean`、方差 `variance`、标准差 `std_dev`（可直接代入 z检验/t检验公式）

**与Python衔接**:
```bash
# 导出用户级明细给Python做统计检验
sqlite3 -header -csv user_behavior.db < 05_ab_test_framework.sql > ../data/ab_test_users.csv
```

---

### 06_anomaly_detection.sql

**用途**: 监控每日核心指标，定位异常波动。

**检测方法**:
1. **3σ原则（全局统计）**: 计算所有日期的均值和标准差，标记 `|z-score| > 2` 的日期
2. **移动平均法（时间序列）**: 使用窗口函数 `ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING` 计算前3日移动平均和标准差，检测当日偏离
3. **小时级异常**: 计算每个小时在所有日期中的统计分布，定位具体异常时段

**异常归因**:
- 周末效应（2017-11-25/26, 12-02/03 为周末）
- 环比变化幅度
- 工作日大幅波动预警

**输出指标**:
- `dau_zscore`, `pv_zscore`, `rate_zscore`: 各指标的标准化得分
- `anomaly_flag`: 异常类型标签
- `possible_reason`: 可能原因推测

---

### 07_product_analysis.sql

**用途**: 商品与类目层面的运营分析。

**分析维度**:
1. **热销商品TOP20**: 按 `buy_count` 排名，使用 `RANK()` 和 `DENSE_RANK()`
2. **热销类目TOP10**: 类目购买量、转化率、SKU数、人均购买量
3. **高转化商品TOP20**: 过滤 `pv_count >= 50` 的商品，按转化率排名（识别潜力爆款）
4. **长尾商品分析**: 定义 `高点击零转化`、`高点击低转化`、`流量浪费型` 商品，识别运营优化点
5. **类目效率对比**: 与全局平均转化率对比，使用窗口函数分档（优秀/良好/一般/低效）
6. **商品关联初步**: 自连接找出被同一用户共同购买的商品对（关联规则基础）

---

## 技术亮点汇总

| 技术点 | 应用脚本 | 说明 |
|--------|----------|------|
| CTE (WITH子句) | 全部 | 提高可读性，模块化复杂查询 |
| 窗口函数 | 02/03/04/06/07 | ROW_NUMBER, RANK, DENSE_RANK, NTILE, LAG, LEAD, 移动平均 |
| 自连接 | 02/05/07 | 留存分析、A/B分组、商品关联 |
| 条件聚合 | 全部 | `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` 实现透视统计 |
| 统计量SQL实现 | 05/06 | 均值、方差、标准差、Z-score 纯SQL计算 |
| 视图封装 | 01 | 将常用指标抽象为视图，简化后续查询 |

---

## 注意事项

1. **SQLite方言限制**:
   - 标准差使用 `SQRT(AVG(x²) - AVG(x)²)` 计算（总体标准差），样本标准差在脚本中通过 `n/(n-1)` 调整
   - 日期计算使用 `JULIANDAY()` 函数，返回天数差
   - `NTILE()` 要求 SQLite 3.25+（2018年后版本均支持）

2. **数据导入检查**:
   ```sql
   -- 导入后执行快速验证
   SELECT COUNT(*) FROM user_behavior;
   SELECT MIN(date), MAX(date) FROM user_behavior;
   SELECT behavior_type, COUNT(*) FROM user_behavior GROUP BY behavior_type;
   ```

3. **性能建议**:
   - 数据量较大时，确保 `01_database_setup.sql` 中的索引已创建
   - 频繁使用的查询建议基于视图 `v_daily_metrics`、`v_item_metrics` 进行二次开发

---

## 扩展建议

- 将 `05_ab_test_framework.sql` 的用户级明细导出为CSV，使用Python的 `scipy.stats` 进行正式的 t检验 / 卡方检验
- 将 `04_rfm_model.sql` 的分层结果与 `03_conversion_funnel.sql` 结合，分析不同价值用户的转化路径差异
- 将 `06_anomaly_detection.sql` 的日报指标接入定时任务，实现自动化监控

---

*作者: SQL数据分析师模块*  
*数据集: 阿里云天池 - 淘宝用户行为数据集*  
*时间范围: 2017-11-25 至 2017-12-03*
