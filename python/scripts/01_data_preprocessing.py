"""
数据预处理脚本
对原始用户行为数据进行清洗、转换和特征工程

使用方法:
    python 01_data_preprocessing.py --input data/raw/UserBehavior.csv --output data/processed/
"""

import argparse
import os
import numpy as np
import pandas as pd
from datetime import datetime


def load_raw_data(filepath):
    """加载原始数据（无header的CSV），针对大数据优化内存"""
    print(f"正在加载数据: {filepath}")
    
    # 真实数据集无header，列名需要手动指定
    column_names = ['user_id', 'item_id', 'category_id', 'behavior_type', 'timestamp']
    
    # 大数据优化：指定dtype减少内存占用
    dtype = {
        'user_id': 'int32',
        'item_id': 'int32', 
        'category_id': 'int32',
        'timestamp': 'int32'
    }
    
    df = pd.read_csv(
        filepath, 
        header=None, 
        names=column_names,
        dtype=dtype
    )
    # behavior_type转为category类型节省内存
    df['behavior_type'] = df['behavior_type'].astype('category')
    
    print(f"✅ 加载完成: {len(df):,} 条记录")
    print(f"  内存占用: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
    return df


def clean_data(df):
    """数据清洗，针对大数据优化"""
    print("\n开始数据清洗...")
    original_count = len(df)
    
    # 1. 删除完全重复的记录
    df = df.drop_duplicates()
    print(f"  去重后: {len(df):,} 条 (删除 {original_count - len(df):,} 条重复)")
    
    # 2. 处理缺失值
    missing_before = df.isnull().sum().sum()
    if missing_before > 0:
        df = df.dropna()
    print(f"  缺失值处理: 删除 {missing_before} 个缺失值")
    
    # 3. 异常值处理 - 时间戳范围检查: 2017-11-25 ~ 2017-12-03
    start_ts = int(datetime(2017, 11, 25).timestamp())
    end_ts = int(datetime(2017, 12, 4).timestamp())
    
    valid_time_mask = (df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts)
    invalid_time = (~valid_time_mask).sum()
    if invalid_time > 0:
        df = df[valid_time_mask]
    print(f"  时间戳过滤: 删除 {invalid_time:,} 条异常时间记录")
    
    # 4. behavior_type 有效性检查
    valid_behaviors = ['pv', 'buy', 'cart', 'fav']
    valid_behavior_mask = df['behavior_type'].isin(valid_behaviors)
    invalid_behavior = (~valid_behavior_mask).sum()
    if invalid_behavior > 0:
        df = df[valid_behavior_mask]
    print(f"  行为类型过滤: 删除 {invalid_behavior:,} 条无效行为记录")
    
    # 5. 内存优化：重置索引并清理碎片
    df = df.reset_index(drop=True)
    
    print(f"\n清洗完成: {len(df):,} 条有效记录")
    print(f"  内存占用: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
    return df


def feature_engineering(df):
    """特征工程：衍生时间相关特征，针对大数据优化"""
    print("\n开始特征工程...")
    
    # 转换时间戳为日期时间（使用unit='s'直接转换，更高效）
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    
    # 衍生时间特征（使用向量化操作，避免apply）
    df['date'] = df['datetime'].dt.date
    df['hour'] = df['datetime'].dt.hour.astype('int8')
    df['day_of_week'] = df['datetime'].dt.dayofweek.astype('int8')  # 0=周一, 6=周日
    df['is_weekend'] = (df['day_of_week'] >= 5).astype('int8')
    
    # 时间段分类（使用向量化条件赋值，避免apply）
    hour = df['hour'].values
    conditions = [
        (hour >= 0) & (hour < 6),
        (hour >= 6) & (hour < 12),
        (hour >= 12) & (hour < 14),
        (hour >= 14) & (hour < 18),
        (hour >= 18) & (hour < 22),
        (hour >= 22)
    ]
    choices = ['凌晨', '上午', '中午', '下午', '晚上', '深夜']
    df['time_period'] = np.select(conditions, choices, default='未知')
    df['time_period'] = df['time_period'].astype('category')
    
    # 内存优化：删除datetime列（可由timestamp重建），保留更轻量的date
    df = df.drop(columns=['datetime'])
    
    print(f"  衍生特征: date, hour, day_of_week, is_weekend, time_period")
    print(f"  内存占用: {df.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
    return df


def save_processed_data(df, output_dir, split_behavior=False):
    """保存处理后的数据
    
    Parameters:
    -----------
    df : pd.DataFrame
        清洗后的数据
    output_dir : str
        输出目录
    split_behavior : bool
        是否按行为类型拆分为单独文件（大数据时建议False以节省磁盘）
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 保存完整清洗数据
    output_path = os.path.join(output_dir, 'user_behavior_cleaned.csv')
    df.to_csv(output_path, index=False)
    print(f"\n✅ 清洗数据已保存: {output_path}")
    
    # 按行为类型拆分（可选，大数据时跳过）
    if split_behavior:
        for behavior in ['pv', 'buy', 'cart', 'fav']:
            subset = df[df['behavior_type'] == behavior]
            if len(subset) > 0:
                subset_path = os.path.join(output_dir, f'user_behavior_{behavior}.csv')
                subset.to_csv(subset_path, index=False)
                print(f"✅ {behavior}行为数据已保存: {subset_path} ({len(subset):,} 条)")
    
    # 生成数据字典
    data_dict = {
        '字段名': ['user_id', 'item_id', 'category_id', 'behavior_type', 'timestamp', 
                  'date', 'hour', 'day_of_week', 'is_weekend', 'time_period'],
        '类型': ['int32', 'int32', 'int32', 'category', 'int32', 
                'date', 'int8', 'int8', 'int8', 'category'],
        '说明': ['用户ID', '商品ID', '商品类目ID', '行为类型(pv/buy/cart/fav)', 'Unix时间戳(秒)',
                '日期', '小时(0-23)', '星期(0=周一)', '是否周末', '时间段']
    }
    dict_df = pd.DataFrame(data_dict)
    dict_path = os.path.join(output_dir, 'data_dictionary.csv')
    dict_df.to_csv(dict_path, index=False, encoding='utf-8-sig')
    print(f"✅ 数据字典已保存: {dict_path}")


def generate_summary_report(df, output_dir):
    """生成数据摘要报告"""
    report_lines = [
        "# 数据预处理报告",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 数据集概览",
        "",
        f"- 总记录数: {len(df):,}",
        f"- 唯一用户数: {df['user_id'].nunique():,}",
        f"- 唯一商品数: {df['item_id'].nunique():,}",
        f"- 唯一类目数: {df['category_id'].nunique():,}",
        f"- 时间范围: {df['date'].min()} ~ {df['date'].max()}",
        "",
        "## 行为分布",
        "",
    ]
    
    behavior_counts = df['behavior_type'].value_counts()
    for behavior, count in behavior_counts.items():
        pct = count / len(df) * 100
        report_lines.append(f"- {behavior}: {count:,} ({pct:.2f}%)")
    
    report_lines.extend([
        "",
        "## 时间分布",
        "",
        f"- 日均活跃用户数: {df.groupby('date')['user_id'].nunique().mean():.0f}",
        f"- 高峰时段: {df.groupby('hour').size().idxmax()}:00",
        f"- 周末流量占比: {df[df['is_weekend']==1].shape[0] / len(df) * 100:.2f}%",
        "",
        "## 关键指标",
        "",
    ])
    
    # 计算转化率
    pv_count = behavior_counts.get('pv', 0)
    buy_count = behavior_counts.get('buy', 0)
    cart_count = behavior_counts.get('cart', 0)
    fav_count = behavior_counts.get('fav', 0)
    
    if pv_count > 0:
        report_lines.append(f"- 点击→购买转化率: {buy_count / pv_count * 100:.4f}%")
        report_lines.append(f"- 点击→加购转化率: {cart_count / pv_count * 100:.4f}%")
        report_lines.append(f"- 点击→收藏转化率: {fav_count / pv_count * 100:.4f}%")
    
    # 复购率
    user_buy_counts = df[df['behavior_type'] == 'buy'].groupby('user_id').size()
    repurchase_rate = (user_buy_counts > 1).sum() / len(user_buy_counts) * 100 if len(user_buy_counts) > 0 else 0
    report_lines.append(f"- 用户复购率: {repurchase_rate:.2f}%")
    
    report_lines.extend(["", "---", "*本报告由数据预处理脚本自动生成*"])
    
    report_path = os.path.join(output_dir, 'preprocessing_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"✅ 摘要报告已保存: {report_path}")


def main():
    parser = argparse.ArgumentParser(description='电商用户行为数据预处理（大数据优化版）')
    parser.add_argument('--input', type=str, default='data/raw/UserBehavior.csv',
                        help='原始数据文件路径')
    parser.add_argument('--output', type=str, default='data/processed/',
                        help='处理后数据输出目录')
    parser.add_argument('--split-behavior', action='store_true',
                        help='按行为类型拆分为单独文件（大数据时慎用）')
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"❌ 错误: 输入文件不存在: {args.input}")
        print("请先下载数据集或运行 generate_mock_data.py 生成模拟数据")
        return
    
    # 执行处理流程
    df = load_raw_data(args.input)
    df = clean_data(df)
    df = feature_engineering(df)
    save_processed_data(df, args.output, split_behavior=args.split_behavior)
    generate_summary_report(df, args.output)
    
    print("\n" + "="*50)
    print("🎉 数据预处理全部完成！")
    print("="*50)
    print(f"\n输出文件:")
    print(f"  - 清洗数据: {args.output}user_behavior_cleaned.csv")
    print(f"  - 数据字典: {args.output}data_dictionary.csv")
    print(f"  - 摘要报告: {args.output}preprocessing_report.md")


if __name__ == '__main__':
    main()
