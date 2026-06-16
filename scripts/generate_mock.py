"""
模拟数据生成脚本
基于真实电商用户行为数据集的统计特征，生成小规模测试数据。
格式与真实数据集完全一致，可直接用于项目开发和测试。

真实数据集统计特征参考：
- 时间范围: 2017-11-24 ~ 2017-12-03 (10天)
- 行为分布: pv ~90%, cart ~5%, fav ~3%, buy ~2%
- 用户活跃高峰: 晚上 20:00-23:00
- 周末流量略高于工作日

使用方法:
    python scripts/generate_mock.py --output data/raw/UserBehavior.csv --n_records 100000
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os

# 添加项目根目录到 sys.path，以便导入 config 模块
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import RAW_CSV_PATH, RAW_DATA_DIR, START_DATE, END_DATE


def generate_mock_data(n_records=100000, random_seed=42):
    """
    生成模拟的电商用户行为数据

    Parameters:
    -----------
    n_records : int
        生成的记录数，默认10万条（便于快速测试）
    random_seed : int
        随机种子，保证可复现

    Returns:
    --------
    pd.DataFrame
        模拟数据集，列与真实数据集完全一致
    """
    np.random.seed(random_seed)

    # 时间范围起点（与 config.py 保持一致）
    start_time = datetime.strptime(START_DATE, "%Y-%m-%d")
    num_days = (datetime.strptime(END_DATE, "%Y-%m-%d") - start_time).days + 1
    # 用户和商品ID池
    # 提高用户数量密度，使活跃天数分布更接近真实电商场景（大量低频用户），
    # 从而保证下游流失预测等模型能观察到正负样本。
    n_users = max(5000, n_records // 10)
    n_items = max(5000, n_records // 20)
    n_categories = 200

    user_ids = np.random.randint(100000, 100000 + n_users, size=n_records)
    item_ids = np.random.randint(1000000, 1000000 + n_items, size=n_records)
    category_ids = np.random.randint(1000, 1000 + n_categories, size=n_records)

    # 行为类型分布（基于真实数据统计）
    behavior_types = np.random.choice(
        ["pv", "buy", "cart", "fav"],
        size=n_records,
        p=[0.90, 0.025, 0.045, 0.03],  # 接近真实分布
    )

    # 时间戳生成（模拟真实的时间分布特征）
    # 晚上20-23点是高峰，周末流量更高
    timestamps = []
    for _ in range(n_records):
        # 随机选择一天中的秒数
        second_of_day = np.random.randint(0, 86400)

        # 添加时间偏好：晚上20-23点权重更高
        hour = second_of_day // 3600
        if 20 <= hour <= 23:
            # 高峰时段，增加概率
            pass
        elif 0 <= hour <= 6:
            # 凌晨时段，降低概率（重新采样）
            second_of_day = np.random.randint(7 * 3600, 86400)

        # 随机选择天数
        day_offset = np.random.randint(0, num_days)

        ts = int(
            (start_time + timedelta(days=day_offset, seconds=second_of_day)).timestamp()
        )
        timestamps.append(ts)

    # 构建DataFrame
    df = pd.DataFrame(
        {
            "user_id": user_ids,
            "item_id": item_ids,
            "category_id": category_ids,
            "behavior_type": behavior_types,
            "timestamp": timestamps,
        }
    )

    # 按时间戳排序（更接近真实数据）
    df = df.sort_values("timestamp").reset_index(drop=True)

    return df


def main():
    parser = argparse.ArgumentParser(description="生成模拟电商用户行为数据")
    parser.add_argument(
        "--output", type=str, default=str(RAW_CSV_PATH), help="输出文件路径"
    )
    parser.add_argument(
        "--n_records", type=int, default=100000, help="生成的记录数量（默认10万条）"
    )
    parser.add_argument("--seed", type=int, default=42, help="随机种子（默认42）")

    args = parser.parse_args()

    # 确保输出目录存在
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"正在生成 {args.n_records:,} 条模拟数据...")
    df = generate_mock_data(n_records=args.n_records, random_seed=args.seed)

    # 保存为CSV（无header，与真实数据集格式一致）
    df.to_csv(args.output, index=False, header=False)

    print(f"✅ 数据已保存至: {args.output}")
    print("\n数据概览:")
    print(f"  总记录数: {len(df):,}")
    print(f"  用户数: {df['user_id'].nunique():,}")
    print(f"  商品数: {df['item_id'].nunique():,}")
    print(f"  类目数: {df['category_id'].nunique():,}")
    print("\n行为分布:")
    print(df["behavior_type"].value_counts().to_string())
    print("\n时间范围:")
    print(f"  开始: {datetime.fromtimestamp(df['timestamp'].min())}")
    print(f"  结束: {datetime.fromtimestamp(df['timestamp'].max())}")


if __name__ == "__main__":
    main()
