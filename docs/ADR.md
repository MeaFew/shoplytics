# Architecture Decision Records

本文件记录项目在技术选型与架构设计上的关键决策, 方便后续维护者和面试官理解设计背景.

---

## ADR-001: 使用 DuckDB 作为本地 OLAP 引擎

**状态**: 已接受

**背景**
项目早期使用 SQLite 存储分析结果. 随着 SQL 分析脚本增多, SQLite 对窗口函数、CTE、CSV 导入的支持较弱, 且与 dbt 集成不自然.

**决策**
将分析层统一迁移到 DuckDB:
- 原生支持窗口函数、`read_csv_auto()`、Parquet 扩展
- dbt-duckdb 提供零配置的数据工程体验
- 单文件数据库, 与 SQLite 一样便于分享和 CI 测试

**后果**
- 正面: SQL 脚本更简洁, dbt 路径统一, 分析性能提升
- 负面: 需要维护 `.sqlfluff` 的 dialect 配置; 迁移时需要改写 SQLite 特有函数 (`JULIANDAY` → `DATE_DIFF`)

---

## ADR-002: Polars 替代 Pandas 作为核心 ETL 工具

**状态**: 已接受

**背景**
淘宝用户行为数据集有 2900 万行. 使用 Pandas 做全量清洗时内存占用高、耗时较长.

**决策**
使用 Polars 作为默认预处理引擎, 保留 Pandas 作为对比和兼容性备选.

**后果**
- 正面: 预处理耗时从数十秒降到约 0.4 秒 (实测因硬件而异)
- 正面: Lazy API 便于未来扩展到更大规模数据集
- 负面: 团队需要熟悉 Polars API; 部分 Pandas 生态工具需要转换

---

## ADR-003: 集中式配置 config.py

**状态**: 已接受

**背景**
项目初期各脚本各自硬编码 `BASE_DIR` 和数据路径, 导致 Windows 与 Linux、本地与 Docker 之间切换困难.

**决策**
引入根目录 `config.py`, 使用 `pathlib.Path` 统一管理:
- `RAW_CSV_PATH`, `CLEANED_CSV_PATH`, `CLEANED_PARQUET_PATH`
- `DUCKDB_PATH`
- `SPARK_INPUT_PATH`, `SPARK_OUTPUT_DIR`

**后果**
- 正面: 所有脚本统一读取配置, 跨平台无感
- 正面: Docker、CI、本地开发共用同一套路径约定
- 负面: PySpark 脚本需要通过 `sys.path.insert` 才能导入根目录模块

---

## ADR-004: 扁平化目录结构

**状态**: 已接受

**背景**
项目最初使用 `python/scripts/` 和 `python/notebooks/` 两层嵌套, 导致 Makefile 和 CI 命令冗长, 且存在历史遗留的废弃脚本.

**决策**
- 删除 `python/` 层级, 将脚本直接放在 `scripts/`, notebooks 放在 `notebooks/`
- 移除已废弃的 pandas 预处理、`generate_report_images.py`、`03_daily_report_generator.py`

**后果**
- 正面: `make` 命令更短, 目录结构一目了然
- 正面: 减少维护负担, 避免新人踩到旧脚本
- 负面: 历史文档和外部引用需要同步更新路径

---

## ADR-005: dbt 用于数据建模而非复杂 ETL

**状态**: 已接受

**背景**
项目包含 SQL 分析脚本、PySpark 脚本和 Python 分析脚本, 需要一层结构化的数据模型来管理依赖.

**决策**
使用 dbt 负责:
- staging 模型: 统一字段命名与类型转换
- intermediate 模型: 清洗与轻度聚合
- marts 模型: 面向业务主题的事实表与维度表

复杂 ETL (如 2900 万行原始 CSV 清洗) 仍由 `scripts/preprocess.py` 完成.

**后果**
- 正面: 数据血缘清晰, 测试用例可以跟模型一起管理
- 正面: 与生产环境 dbt + Snowflake/BigQuery 模式对齐
- 负面: 本地开发需要安装 dbt-duckdb, 增加初始化成本
