# dbt 项目：拼多多电商数据分析

## 什么是 dbt？

dbt（data build tool）是一个数据转换工具，它让数据分析师和工程师能够用软件工程的最佳实践（版本控制、测试、文档）来管理数据转换流程。

核心特点：
- **SQL 为中心**：所有转换逻辑用 SQL 编写
- **模块化**：通过 `ref()` 函数建立模型依赖，形成数据血缘
- **可测试**：内置数据质量测试框架
- **自动生成文档**：一键生成数据字典和血缘图
- **版本控制友好**：纯文本 SQL + YAML 配置，天然适配 Git

---

## 项目结构

```
dbt/
├── dbt_project.yml              # dbt 项目主配置
├── profiles.yml                 # 数据库连接配置（DuckDB）
├── models/
│   ├── staging/
│   │   ├── stg_user_behavior.sql    # 清洗层：原始CSV加载与类型转换
│   │   └── schema.yml               # 模型文档与测试
│   ├── intermediate/
│   │   ├── int_user_daily_metrics.sql   # 日级指标（DAU、PV、转化率）
│   │   ├── int_user_retention.sql       # 留存分析（次日/3日/7日留存）
│   │   ├── int_conversion_funnel.sql    # 转化漏斗
│   │   └── schema.yml
│   └── marts/
│       ├── mart_daily_kpi.sql       # 核心KPI宽表（面向业务）
│       ├── mart_user_segments.sql   # 用户分层宽表（RFM）
│       └── schema.yml
├── tests/
│   ├── assert_unique_user_id.sql
│   ├── assert_non_null_behavior.sql
│   ├── assert_valid_timestamp.sql
│   └── assert_positive_counts.sql
└── README.md
```

---

## 数据血缘（Lineage）

```
原始CSV
    │
    ▼
stg_user_behavior (staging)
    │
    ├──────────────┬──────────────┐
    ▼              ▼              ▼
int_user_daily_metrics  int_user_retention  int_conversion_funnel
(intermediate)          (intermediate)      (intermediate)
    │              │              │
    └──────────────┴──────────────┘
                   │
                   ▼
        ┌─────────────────┐
        ▼                 ▼
  mart_daily_kpi    mart_user_segments
      (marts)           (marts)
```

---

## 环境准备

### 1. 安装 dbt-duckdb

```bash
pip install dbt-duckdb
```

### 2. 配置 profiles.yml

本项目已提供 `profiles.yml`，使用 DuckDB 作为本地分析引擎：

- **数据库文件**：`pdd_analytics.duckdb`（本地文件，无需服务器）
- **线程数**：4
- **内存限制**：4GB

> 注意：`profiles.yml` 默认放在 `~/.dbt/profiles.yml`（全局）或本项目根目录（局部）。
> 如果 dbt 找不到 profile，请复制本项目 `profiles.yml` 到 `~/.dbt/` 目录，或运行：
> ```bash
> export DBT_PROFILES_DIR=.
> ```

---

## 常用命令

### 运行模型

```bash
# 运行所有模型
dbt run

# 运行指定层
dbt run --select staging
dbt run --select intermediate
dbt run --select marts

# 运行指定模型
dbt run --select mart_daily_kpi

# 全量刷新（忽略增量）
dbt run --full-refresh
```

### 运行测试

```bash
# 运行所有测试（schema.yml 中的测试 + tests/ 目录中的自定义测试）
dbt test

# 运行指定模型的测试
dbt test --select stg_user_behavior

# 仅运行自定义测试
dbt test --select test_type:generic
dbt test --select test_type:singular
```

### 生成文档

```bash
# 生成文档静态站点
dbt docs generate

# 启动本地文档服务器（默认端口 8080）
dbt docs serve
```

浏览器打开 `http://localhost:8080` 即可查看：
- 数据血缘图
- 模型文档
- 列级说明
- 测试结果

### 编译 SQL（不执行）

```bash
# 查看编译后的 SQL
dbt compile

# 查看指定模型编译结果
dbt compile --select int_user_daily_metrics
```

---

## 模型说明

| 模型 | 层级 | 说明 |
|------|------|------|
| `stg_user_behavior` | staging | 从CSV加载，类型转换，过滤无效数据 |
| `int_user_daily_metrics` | intermediate | 每日DAU、PV、购买/加购/收藏量、转化率 |
| `int_user_retention` | intermediate | 每日新增用户，次日/3日/7日留存率 |
| `int_conversion_funnel` | intermediate | 点击→收藏→加购→购买漏斗，路径分析 |
| `mart_daily_kpi` | marts | 核心KPI宽表，含环比变化和3σ异常标记 |
| `mart_user_segments` | marts | RFM分层、用户标签、生命周期阶段 |

---

## 测试说明

| 测试文件 | 说明 |
|----------|------|
| `assert_unique_user_id.sql` | 检查同一用户对同一商品单日行为是否异常过量 |
| `assert_non_null_behavior.sql` | 检查 behavior_type 非空且值合法 |
| `assert_valid_timestamp.sql` | 检查时间戳在有效范围内 |
| `assert_positive_counts.sql` | 检查所有指标计数非负 |

此外，`schema.yml` 中还定义了以下内置测试：
- `not_null`：关键字段非空
- `unique`：日期/用户ID唯一性
- `accepted_values`：behavior_type 枚举值检查

---

## 技术栈

- **dbt-core**: 数据转换框架
- **dbt-duckdb**: DuckDB 适配器（单机分析，零配置）
- **DuckDB**: 嵌入式分析型数据库
- **数据集**: 阿里云天池淘宝用户行为数据集（2017-11-24 ~ 2017-12-03）

---

## 注意事项

1. **数据路径**：`dbt_project.yml` 中的 `vars.data_path` 已配置为绝对路径，如移动项目请相应修改。
2. **DuckDB 并发**：DuckDB 为嵌入式数据库，不支持多进程并发写入，dbt 线程数已设为4用于读取并行。
3. **日期硬编码**：留存分析中数据截止日期 `2017-12-03` 为硬编码，如更换数据集请修改 `mart_user_segments.sql`。
4. **首次运行**：首次 `dbt run` 会创建 `pdd_analytics.duckdb` 数据库文件，后续运行将复用该文件。

---

## 作者

2026 数据工程师 | 拼多多数据分析师求职项目
