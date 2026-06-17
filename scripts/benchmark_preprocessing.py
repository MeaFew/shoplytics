"""
benchmark_preprocessing.py
预处理性能基准测试

对比 Polars 和 Pandas 在淘宝 2900 万条用户行为数据上的清洗性能.
结果保存到 reports/preprocessing_benchmark.json 供 README 引用.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import polars as pl

from config import PROJECT_ROOT, RAW_CSV_PATH, REPORTS_DIR


def pandas_pipeline(csv_path: Path) -> dict[str, float]:
    """使用 Pandas 执行基础清洗并计时."""
    t0 = time.perf_counter()
    df = pd.read_csv(
        csv_path,
        header=None,
        names=["user_id", "item_id", "category_id", "behavior_type", "timestamp"],
    )
    df["date"] = pd.to_datetime(df["timestamp"], unit="s").dt.date
    df["hour"] = pd.to_datetime(df["timestamp"], unit="s").dt.hour
    df["day_of_week"] = pd.to_datetime(df["timestamp"], unit="s").dt.weekday
    df["is_weekend"] = df["day_of_week"].apply(lambda x: 1 if x >= 5 else 0)
    # NOTE: time_period划分与 preprocess.py 保持一致（6档中文标签）
    df["time_period"] = pd.cut(
        df["hour"],
        bins=[-1, 6, 12, 14, 18, 22, 24],
        labels=["凌晨", "上午", "中午", "下午", "晚上", "深夜"],
    ).astype(str)
    elapsed = time.perf_counter() - t0
    return {"rows": len(df), "elapsed_seconds": round(elapsed, 3)}


def polars_pipeline(csv_path: Path) -> dict[str, float]:
    """使用 Polars 执行基础清洗并计时."""
    t0 = time.perf_counter()
    df = pl.read_csv(
        csv_path,
        has_header=False,
        new_columns=["user_id", "item_id", "category_id", "behavior_type", "timestamp"],
    )
    df = df.with_columns(
        pl.from_epoch("timestamp", time_unit="s").dt.date().alias("date"),
        pl.from_epoch("timestamp", time_unit="s").dt.hour().alias("hour"),
        pl.from_epoch("timestamp", time_unit="s").dt.weekday().alias("day_of_week"),
    )
    df = df.with_columns(
        pl.when(pl.col("day_of_week") >= 5).then(1).otherwise(0).alias("is_weekend"),
        # NOTE: time_period划分与 preprocess.py 保持一致（6档中文标签）
        pl.when(pl.col("hour") < 6)
        .then(pl.lit("凌晨"))
        .when(pl.col("hour") < 12)
        .then(pl.lit("上午"))
        .when(pl.col("hour") < 14)
        .then(pl.lit("中午"))
        .when(pl.col("hour") < 18)
        .then(pl.lit("下午"))
        .when(pl.col("hour") < 22)
        .then(pl.lit("晚上"))
        .otherwise(pl.lit("深夜"))
        .alias("time_period"),
    )
    elapsed = time.perf_counter() - t0
    return {"rows": len(df), "elapsed_seconds": round(elapsed, 3)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark Polars vs Pandas preprocessing"
    )
    parser.add_argument("--input", type=Path, default=RAW_CSV_PATH)
    parser.add_argument(
        "--output", type=Path, default=REPORTS_DIR / "preprocessing_benchmark.json"
    )
    parser.add_argument(
        "--pandas", action="store_true", help="Also run Pandas benchmark"
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"输入文件不存在: {args.input}")
        print("请先生成或下载数据, 再运行 benchmark.")
        return 1

    print(f"Running Polars benchmark on {args.input} ...")
    polars_result = polars_pipeline(args.input)
    print(
        f"Polars: {polars_result['elapsed_seconds']:.3f}s for {polars_result['rows']:,} rows"
    )

    pandas_result = None
    if args.pandas:
        print(f"\nRunning Pandas benchmark on {args.input} ...")
        pandas_result = pandas_pipeline(args.input)
        print(
            f"Pandas: {pandas_result['elapsed_seconds']:.3f}s for {pandas_result['rows']:,} rows"
        )
        speedup = pandas_result["elapsed_seconds"] / polars_result["elapsed_seconds"]
        print(f"Speedup (Pandas / Polars): {speedup:.1f}x")

    report = {
        "polars": polars_result,
        "pandas": pandas_result,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n结果已保存: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
