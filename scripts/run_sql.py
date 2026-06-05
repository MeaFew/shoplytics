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


def split_sql_statements(content: str) -> list[str]:
    """按分号分隔 SQL 语句，跳过注释和字符串字面量中的分号。

    支持:
      - 行注释 ``-- ...``
      - 块注释 ``/* ... */``
      - 单引号字符串 ``'...'``（支持 ``''`` 转义）
      - 双引号字符串 ``"..."``（支持 ``""`` 转义）
    """
    statements: list[str] = []
    start = 0
    i = 0
    length = len(content)

    while i < length:
        c = content[i]

        # 行注释 -- ...
        if c == '-' and i + 1 < length and content[i + 1] == '-':
            i += 2
            while i < length and content[i] != '\n':
                i += 1
            continue

        # 块注释 /* ... */
        if c == '/' and i + 1 < length and content[i + 1] == '*':
            i += 2
            while i + 1 < length and not (content[i] == '*' and content[i + 1] == '/'):
                i += 1
            i += 2  # skip */
            continue

        # 单引号字符串
        if c == "'":
            i += 1
            while i < length:
                if content[i] == "'" and i + 1 < length and content[i + 1] == "'":
                    i += 2  # escaped quote ''
                elif content[i] == "'":
                    i += 1
                    break
                else:
                    i += 1
            continue

        # 双引号字符串
        if c == '"':
            i += 1
            while i < length:
                if content[i] == '"' and i + 1 < length and content[i + 1] == '"':
                    i += 2  # escaped quote ""
                elif content[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
            continue

        # 分号分隔
        if c == ';':
            stmt = content[start:i].strip()
            if stmt:
                statements.append(stmt)
            start = i + 1

        i += 1

    # 最后一条（可能没有分号结尾）
    remainder = content[start:].strip()
    if remainder:
        statements.append(remainder)

    return statements


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

        # 逐条执行（注释/引号感知分号分隔），跳过空语句和纯注释
        statements = split_sql_statements(sql)
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
