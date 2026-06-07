# -*- coding: utf-8 -*-
"""
validate_data.py
数据质量校验脚本

功能:
    1. 读取 data/processed/user_behavior_cleaned.csv
    2. 检查必填字段、数据类型、取值范围
    3. 校验行为类型分布和日期范围
    4. 输出校验报告; 发现严重问题时返回非零退出码

用法:
    python scripts/validate_data.py
    python scripts/validate_data.py --path data/processed/user_behavior_cleaned.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl

from config import CLEANED_CSV_PATH

EXPECTED_COLUMNS = {
    "user_id": pl.Int64,
    "item_id": pl.Int64,
    "category_id": pl.Int64,
    "behavior_type": pl.Utf8,
    "timestamp": pl.Int64,
    "date": pl.Utf8,  # CSV 中 date 为 YYYY-MM-DD 字符串
    "hour": pl.Int64,
    "day_of_week": pl.Int64,
    "is_weekend": pl.Int64,
    "time_period": pl.Utf8,
}

EXPECTED_BEHAVIORS = {"pv", "buy", "cart", "fav"}
DATE_RANGE = ("2017-11-24", "2017-12-03")


def validate(path: Path) -> list[str]:
    """对清洗后的数据集执行校验, 返回错误列表."""
    errors: list[str] = []

    if not path.exists():
        errors.append(f"文件不存在: {path}")
        return errors

    try:
        df = pl.read_csv(path)
    except Exception as exc:  # pragma: no cover - broad on purpose for robust validation
        errors.append(f"无法读取 CSV: {exc}")
        return errors

    # 1. 列名校验
    missing = set(EXPECTED_COLUMNS.keys()) - set(df.columns)
    if missing:
        errors.append(f"缺少列: {sorted(missing)}")

    extra = set(df.columns) - set(EXPECTED_COLUMNS.keys())
    if extra:
        errors.append(f"多余列: {sorted(extra)}")

    # 2. 类型校验 (Polars 读 CSV 时类型可能不同, 只校验关键列)
    for col_name, expected_dtype in EXPECTED_COLUMNS.items():
        if col_name not in df.columns:
            continue
        actual = df[col_name].dtype
        if actual != expected_dtype:
            # 允许整数类型的互相兼容
            if expected_dtype == pl.Int64 and "Int" in str(actual):
                continue
            errors.append(f"列 '{col_name}' 类型不匹配: 期望 {expected_dtype}, 实际 {actual}")

    # 3. 空值校验
    for col_name in EXPECTED_COLUMNS.keys():
        if col_name not in df.columns:
            continue
        null_count = df[col_name].null_count()
        if null_count > 0:
            errors.append(f"列 '{col_name}' 存在 {null_count} 个空值")

    # 4. 行为类型校验
    if "behavior_type" in df.columns:
        actual_behaviors = set(df["behavior_type"].unique().to_list())
        unexpected = actual_behaviors - EXPECTED_BEHAVIORS
        if unexpected:
            errors.append(f"未知行为类型: {unexpected}")

        behavior_counts = df["behavior_type"].value_counts()
        print("行为类型分布:")
        print(behavior_counts)

    # 5. 日期范围校验
    if "date" in df.columns:
        min_date = df["date"].min()
        max_date = df["date"].max()
        print(f"\n日期范围: {min_date} ~ {max_date}")
        if str(min_date) < DATE_RANGE[0] or str(max_date) > DATE_RANGE[1]:
            errors.append(f"日期超出预期范围 {DATE_RANGE}")

    # 6. 基础统计
    n_rows = len(df)
    n_users = df["user_id"].n_unique() if "user_id" in df.columns else 0
    n_items = df["item_id"].n_unique() if "item_id" in df.columns else 0
    print(f"\n总记录数: {n_rows:,}")
    print(f"用户数: {n_users:,}")
    print(f"商品数: {n_items:,}")

    if n_rows == 0:
        errors.append("数据集为空")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate processed user behavior dataset")
    parser.add_argument("--path", type=Path, default=CLEANED_CSV_PATH, help="Path to cleaned CSV")
    args = parser.parse_args()

    print(f"正在校验: {args.path}\n")
    errors = validate(args.path)

    if errors:
        print("\n校验失败:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("\n校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
