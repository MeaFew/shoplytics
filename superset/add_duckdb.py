#!/usr/bin/env python3
"""
Superset DuckDB 数据源自动配置脚本
在容器初始化时运行，将项目的 DuckDB 数据库添加为 Superset 数据源
"""

import os
import sys

# 确保能导入 Superset 模块
sys.path.insert(0, "/app")

from superset import db
from superset.models.core import Database

DUCKDB_PATH = "/app/data/analytics.duckdb"

def add_duckdb_database():
    """将 DuckDB 添加为 Superset 数据源。"""

    # 检查数据库文件是否存在
    if not os.path.exists(DUCKDB_PATH):
        print(f"警告: DuckDB 文件不存在: {DUCKDB_PATH}")
        print("请先运行数据预处理管线生成 analytics.duckdb")
        return

    # 检查是否已存在
    existing = db.session.query(Database).filter_by(database_name="E-commerce DuckDB").first()
    if existing:
        print("DuckDB 数据源已存在，跳过")
        return

    # 创建数据库连接
    database = Database(
        database_name="E-commerce DuckDB",
        sqlalchemy_uri=f"duckdb:///{DUCKDB_PATH}",
        expose_in_sqllab=True,
        allow_ctas=True,
        allow_cvas=True,
        allow_dml=True,
    )

    db.session.add(database)
    db.session.commit()

    print(f"✓ DuckDB 数据源已添加: {DUCKDB_PATH}")
    print("  可在 SQL Lab 中执行查询，或在 Explore 中创建图表")

if __name__ == "__main__":
    try:
        add_duckdb_database()
    except Exception as e:
        print(f"添加 DuckDB 数据源时出错: {e}")
        # 不中断初始化流程
        sys.exit(0)
