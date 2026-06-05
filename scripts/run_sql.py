#!/usr/bin/env python3
"""
SQL 脚本批量执行器（DuckDB）

功能：
    1. 连接到 DuckDB 数据库（自动创建）
    2. 按文件名排序依次执行 sql/ 目录下的所有 .sql 脚本
    3. 输出每条 SQL 的执行状态

用法：
    python scripts/run_sql.py
    python scripts/run_sql.py --db data/processed/analytics.duckdb
"""

import argparse
import sys
from pathlib import Path

import duckdb

from config import DUCKDB_PATH, PROJECT_ROOT

SQL_DIR = PROJECT_ROOT / "sql"


def run_sql_scripts(db_path: Path) -> None:
    """依次执行 sql/ 目录下所有 .sql 文件。"""
    sql_files = sorted(SQL_DIR.glob("*.sql"))
    if not sql_files:
        print(f"未找到 SQL 文件: {SQL_DIR}", file=sys.stderr)
        sys.exit(1)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))

    print(f"连接到 DuckDB: {db_path}")
    print(f"发现 {len(sql_files)} 个 SQL 脚本，开始执行...\n")

    for sql_file in sql_files:
        print(f"  → {sql_file.name} ... ", end="", flush=True)
        sql = sql_file.read_text(encoding="utf-8")

        # 逐条执行（分号分隔），跳过空语句和纯注释
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        for stmt in statements:
            # 跳过以 -- 开头的注释块
            lines = [ln for ln in stmt.splitlines() if ln.strip() and not ln.strip().startswith("--")]
            if not lines:
                continue
            try:
                con.execute(stmt)
            except Exception as exc:
                print(f"FAIL\n    错误: {exc}")
                con.close()
                sys.exit(1)
        print("OK")

    con.close()
    print(f"\n全部 SQL 脚本执行完成。数据库: {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="批量执行 SQL 脚本到 DuckDB")
    parser.add_argument("--db", type=Path, default=DUCKDB_PATH, help="DuckDB 数据库路径")
    args = parser.parse_args()
    run_sql_scripts(args.db)


if __name__ == "__main__":
    main()
