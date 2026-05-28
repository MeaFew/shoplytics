# Contributing Guide

感谢你对本项目的兴趣. 本指南面向希望本地运行、调试或扩展该电商用户行为分析项目的开发者.

## 环境准备

```bash
# 1. 克隆仓库
git clone https://github.com/MeaFew/ecommerce-user-analytics.git
cd ecommerce-user-analytics

# 2. 创建虚拟环境 (推荐 Python 3.12)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt
```

## 数据准备

项目使用阿里云天池 — 淘宝用户行为数据集. 请自行下载并放入 `data/raw/UserBehavior.csv`.

```bash
# 运行预处理
python scripts/preprocess.py --input data/raw/UserBehavior.csv --output data/processed/

# 验证清洗结果
python scripts/validate_data.py
```

## 本地工作流

```bash
# 1. 数据预处理
make preprocess

# 2. 运行 SQL 分析 (DuckDB)
make sql

# 3. 运行 dbt 模型
make dbt

# 4. 运行分析流水线
make pipeline

# 5. 启动看板
make dashboard
```

## 代码规范

提交前请确保通过以下检查:

```bash
# Python lint
ruff check scripts/ dashboard/ pyspark/ --ignore E501,F401,E402

# SQL lint
sqlfluff lint sql/

# 单元测试
pytest tests/ -v
```

## 提交规范

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档更新
- `refactor:` 重构
- `ci:` 持续集成相关
- `test:` 测试相关

## 扩展建议

- 新增 SQL 分析脚本: 放在 `sql/` 并按 `0X_topic.sql` 命名
- 新增 Python 工具脚本: 放在 `scripts/` 并从 `config.py` 读取路径
- 新增 dbt 模型: 放在 `dbt/models/{staging,intermediate,marts}/`
- 新增 notebook: 放在 `notebooks/` 并更新 README 索引
