"""
generate_report_images.py
一键生成项目所有核心分析图表，保存到 images/ 目录

使用方法:
    cd python/scripts
    python generate_report_images.py

依赖:
    polars, pandas, numpy, matplotlib, seaborn, scikit-learn, xgboost
"""

import os
import sys
import time

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMG_DIR = os.path.join(PROJECT_ROOT, "images")
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "user_behavior_cleaned.csv")

os.makedirs(IMG_DIR, exist_ok=True)

if not os.path.exists(DATA_PATH):
    print(f"[ERROR] 数据文件不存在: {DATA_PATH}")
    print("请先运行数据预处理脚本生成清洗数据")
    sys.exit(1)

print(f"使用数据: {DATA_PATH}")
print(f"输出目录: {IMG_DIR}")

# 优先使用 Polars，回退到 Pandas
try:
    import polars as pl
    USE_POLARS = True
    print("[INFO] 使用 Polars 高性能模式")
except ImportError:
    import pandas as pd
    USE_POLARS = False
    print("[INFO] Polars 未安装，回退到 Pandas")

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import timedelta

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style('whitegrid')

# ========== 1. 加载数据 ==========
print("\n[1/7] 加载数据...")
start = time.time()

if USE_POLARS:
    df = pl.read_csv(DATA_PATH)
    if df['date'].dtype == pl.Utf8:
        df = df.with_columns(pl.col('date').str.to_date().alias('date'))
    max_date = df['date'].max()
    min_date = df['date'].min()
else:
    df = pd.read_csv(DATA_PATH, parse_dates=['date'])
    max_date = df['date'].max()
    min_date = df['date'].min()

print(f"  加载完成: {len(df):,} 条, 耗时 {time.time()-start:.1f}s")
print(f"  日期范围: {min_date.date() if hasattr(min_date, 'date') else min_date} ~ {max_date.date() if hasattr(max_date, 'date') else max_date}")

# ========== 辅助函数 ==========
def savefig(name):
    path = os.path.join(IMG_DIR, name)
    plt.savefig(path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  ✓ {name}")

# ========== 2. EDA 图表 ==========
print("\n[2/7] 生成 EDA 图表...")

# 2.1 行为分布饼图
if USE_POLARS:
    behavior_counts = df.group_by('behavior_type').agg(pl.len().alias('count')).sort('count', descending=True)
    labels = behavior_counts['behavior_type'].to_list()
    sizes = behavior_counts['count'].to_list()
else:
    behavior_counts = df['behavior_type'].value_counts()
    labels = behavior_counts.index.tolist()
    sizes = behavior_counts.values.tolist()

fig, ax = plt.subplots(figsize=(8, 6))
colors = ['#D4A373', '#E07A5F', '#F4A261', '#A44A4A']
ax.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
ax.set_title('User Behavior Distribution', fontsize=14, fontweight='bold')
savefig('01_behavior_distribution.png')

# 2.2 DAU 趋势
if USE_POLARS:
    dau = df.group_by('date').agg(pl.col('user_id').n_unique().alias('DAU')).sort('date')
    dates = [str(d) for d in dau['date'].to_list()]
    values = dau['DAU'].to_list()
else:
    dau = df.groupby('date')['user_id'].nunique().reset_index().sort_values('date')
    dates = dau['date'].astype(str).tolist()
    values = dau['user_id'].tolist()

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(dates, values, marker='o', color='#E07A5F', linewidth=2, markersize=6)
ax.fill_between(dates, values, alpha=0.3, color='#E07A5F')
ax.set_title('Daily Active Users (DAU) Trend', fontsize=14, fontweight='bold')
ax.set_xlabel('Date')
ax.set_ylabel('DAU')
ax.tick_params(axis='x', rotation=45)
savefig('01_dau_trend.png')

# 2.3 小时分布热力图
if USE_POLARS:
    hourly = df.group_by(['hour', 'behavior_type']).agg(pl.len().alias('count'))
    hourly_pd = hourly.to_pandas().pivot(index='hour', columns='behavior_type', values='count').fillna(0)
else:
    hourly_pd = df.groupby(['hour', 'behavior_type']).size().unstack(fill_value=0)

fig, ax = plt.subplots(figsize=(10, 6))
sns.heatmap(hourly_pd, cmap='YlOrRd', annot=False, fmt='.0f', ax=ax, cbar_kws={'label': 'Count'})
ax.set_title('Hourly Behavior Distribution Heatmap', fontsize=14, fontweight='bold')
ax.set_xlabel('Behavior Type')
ax.set_ylabel('Hour of Day')
savefig('01_hourly_heatmap.png')

# ========== 3. 转化漏斗图 ==========
print("\n[3/7] 生成转化漏斗图...")

if USE_POLARS:
    funnel_counts = df.filter(pl.col('behavior_type').is_in(['pv', 'fav', 'cart', 'buy'])) \
        .group_by('behavior_type').agg(pl.len().alias('count'))
    funnel_dict = {row[0]: row[1] for row in funnel_counts.iter_rows()}
else:
    funnel_counts = df[df['behavior_type'].isin(['pv', 'fav', 'cart', 'buy'])]['behavior_type'].value_counts()
    funnel_dict = funnel_counts.to_dict()

order = ['pv', 'fav', 'cart', 'buy']
labels_funnel = ['Page View', 'Favorite', 'Add to Cart', 'Purchase']
values_funnel = [funnel_dict.get(b, 0) for b in order]

fig, ax = plt.subplots(figsize=(10, 6))
colors_funnel = ['#D4A373', '#E8A87C', '#F4A261', '#A44A4A']
y_pos = np.arange(len(labels_funnel))
bars = ax.barh(y_pos, values_funnel, color=colors_funnel, height=0.6)
ax.set_yticks(y_pos)
ax.set_yticklabels(labels_funnel)
ax.invert_yaxis()
ax.set_xlabel('Count')
ax.set_title('Conversion Funnel (PV → Fav → Cart → Buy)', fontsize=14, fontweight='bold')
for i, (bar, val) in enumerate(zip(bars, values_funnel)):
    rate = 100.0 if i == 0 else val / values_funnel[0] * 100
    ax.text(val + max(values_funnel)*0.02, bar.get_y() + bar.get_height()/2,
            f'{val:,.0f} ({rate:.2f}%)', va='center', fontsize=10)
savefig('03_conversion_funnel.png')

# ========== 4. RFM 用户分层 ==========
print("\n[4/7] 生成 RFM 用户分层图...")

if USE_POLARS:
    user_stats = df.group_by('user_id').agg([
        pl.count().alias('total_actions'),
        pl.col('date').max().alias('last_date'),
        pl.col('date').n_unique().alias('active_days'),
        pl.col('behavior_type').filter(pl.col('behavior_type') == 'buy').count().alias('buy_count')
    ])
    user_stats = user_stats.with_columns(
        (pl.lit(max_date) - pl.col('last_date')).dt.total_days().alias('recency_days')
    )
    n_users = user_stats.shape[0]
    user_stats = user_stats.with_columns([
        (5 - (pl.col('recency_days').rank('ordinal') * 5 / n_users).cast(pl.Int32).clip(1, 5)).alias('r_score'),
        ((pl.col('total_actions').rank('ordinal') * 5 / n_users).cast(pl.Int32).clip(1, 5)).alias('f_score')
    ])
    user_stats = user_stats.with_columns(
        pl.when((pl.col('r_score') >= 4) & (pl.col('f_score') >= 4)).then(pl.lit('高价值用户'))
        .when((pl.col('r_score') >= 3) & (pl.col('f_score') >= 3)).then(pl.lit('活跃用户'))
        .when((pl.col('r_score') >= 3) & (pl.col('f_score') <= 2)).then(pl.lit('新用户/回流'))
        .when((pl.col('r_score') <= 2) & (pl.col('f_score') >= 3)).then(pl.lit('沉睡用户'))
        .when((pl.col('r_score') <= 2) & (pl.col('f_score') <= 2)).then(pl.lit('流失风险'))
        .otherwise(pl.lit('一般用户')).alias('segment')
    )
    segment_counts = user_stats.group_by('segment').agg(pl.count().alias('count')).sort('count', descending=True)
    seg_labels = segment_counts['segment'].to_list()
    seg_values = segment_counts['count'].to_list()
else:
    user_stats = df.groupby('user_id').agg(
        total_actions=('behavior_type', 'size'),
        last_date=('date', 'max'),
        active_days=('date', 'nunique'),
        buy_count=('behavior_type', lambda x: (x == 'buy').sum())
    ).reset_index()
    user_stats['recency_days'] = (max_date - user_stats['last_date']).dt.days
    user_stats['r_score'] = pd.qcut(user_stats['recency_days'], 5, labels=[5,4,3,2,1]).astype(int)
    user_stats['f_score'] = pd.qcut(user_stats['total_actions'].rank(method='first'), 5, labels=[1,2,3,4,5]).astype(int)
    def segment_fn(row):
        if row['r_score'] >= 4 and row['f_score'] >= 4: return '高价值用户'
        if row['r_score'] >= 3 and row['f_score'] >= 3: return '活跃用户'
        if row['r_score'] >= 3 and row['f_score'] <= 2: return '新用户/回流'
        if row['r_score'] <= 2 and row['f_score'] >= 3: return '沉睡用户'
        if row['r_score'] <= 2 and row['f_score'] <= 2: return '流失风险'
        return '一般用户'
    user_stats['segment'] = user_stats.apply(segment_fn, axis=1)
    segment_counts = user_stats['segment'].value_counts()
    seg_labels = segment_counts.index.tolist()
    seg_values = segment_counts.values.tolist()

fig, ax = plt.subplots(figsize=(8, 6))
colors_seg = ['#A44A4A', '#E07A5F', '#F4A261', '#E9C46A', '#C38D9E', '#D4A373']
ax.pie(seg_values, labels=seg_labels, autopct='%1.1f%%', colors=colors_seg[:len(seg_labels)], startangle=90)
ax.set_title('User Value Segmentation (RF Model)', fontsize=14, fontweight='bold')
savefig('04_rfm_segments.png')

# ========== 5. 流失预测模型 ==========
print("\n[5/7] 生成流失预测图表...")

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_curve, roc_auc_score
from sklearn.ensemble import GradientBoostingClassifier

churn_threshold = max_date - timedelta(days=2)

if USE_POLARS:
    features_df = df.group_by('user_id').agg([
        pl.col('behavior_type').filter(pl.col('behavior_type') == 'pv').count().alias('total_pv'),
        pl.col('behavior_type').filter(pl.col('behavior_type') == 'buy').count().alias('total_buy'),
        pl.col('behavior_type').filter(pl.col('behavior_type') == 'cart').count().alias('total_cart'),
        pl.col('behavior_type').filter(pl.col('behavior_type') == 'fav').count().alias('total_fav'),
        pl.col('date').n_unique().alias('active_days'),
        pl.col('hour').n_unique().alias('active_hours'),
        pl.col('date').max().alias('last_date'),
        pl.col('is_weekend').mean().alias('weekend_ratio')
    ])
    features_df = features_df.with_columns([
        (pl.lit(max_date) - pl.col('last_date')).dt.total_days().alias('recency_days'),
        (pl.col('total_buy') / (pl.col('total_pv') + 1)).alias('buy_conversion'),
        (pl.col('total_cart') / (pl.col('total_pv') + 1)).alias('cart_conversion'),
        (pl.col('total_fav') / (pl.col('total_pv') + 1)).alias('fav_conversion')
    ])
    last3_users = df.filter(pl.col('date') >= churn_threshold).select(pl.col('user_id').unique())
    last3_set = set(last3_users['user_id'].to_list())
    features_df = features_df.with_columns(
        pl.col('user_id').is_in(last3_set).alias('has_recent_activity')
    )
    features_df = features_df.with_columns(
        (~pl.col('has_recent_activity')).cast(pl.Int32).alias('churn')
    )
    fpd = features_df.to_pandas()
else:
    features_df = df.groupby('user_id').agg(
        total_pv=('behavior_type', lambda x: (x == 'pv').sum()),
        total_buy=('behavior_type', lambda x: (x == 'buy').sum()),
        total_cart=('behavior_type', lambda x: (x == 'cart').sum()),
        total_fav=('behavior_type', lambda x: (x == 'fav').sum()),
        active_days=('date', 'nunique'),
        active_hours=('hour', 'nunique'),
        last_date=('date', 'max'),
        weekend_ratio=('is_weekend', 'mean')
    ).reset_index()
    features_df['recency_days'] = (max_date - features_df['last_date']).dt.days
    features_df['buy_conversion'] = features_df['total_buy'] / (features_df['total_pv'] + 1)
    features_df['cart_conversion'] = features_df['total_cart'] / (features_df['total_pv'] + 1)
    features_df['fav_conversion'] = features_df['total_fav'] / (features_df['total_pv'] + 1)
    last3_set = set(df[df['date'] >= churn_threshold]['user_id'].unique())
    features_df['churn'] = (~features_df['user_id'].isin(last3_set)).astype(int)
    fpd = features_df

feature_cols = ['total_pv', 'total_buy', 'total_cart', 'total_fav',
                'active_days', 'active_hours', 'recency_days',
                'weekend_ratio', 'buy_conversion', 'cart_conversion', 'fav_conversion']
X = fpd[feature_cols]
y = fpd['churn']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)
lr = LogisticRegression(max_iter=1000, random_state=42)
lr.fit(X_train_s, y_train)
y_prob_lr = lr.predict_proba(X_test_s)[:, 1]

# 用 GradientBoosting 替代 XGBoost（避免依赖）
gb = GradientBoostingClassifier(n_estimators=200, max_depth=5, random_state=42)
gb.fit(X_train, y_train)
y_prob_gb = gb.predict_proba(X_test)[:, 1]

fpr_lr, tpr_lr, _ = roc_curve(y_test, y_prob_lr)
fpr_gb, tpr_gb, _ = roc_curve(y_test, y_prob_gb)
auc_lr = roc_auc_score(y_test, y_prob_lr)
auc_gb = roc_auc_score(y_test, y_prob_gb)

fig, ax = plt.subplots(figsize=(8, 6))
ax.plot(fpr_lr, tpr_lr, label=f'Logistic Regression (AUC={auc_lr:.3f})', color='#E07A5F', linewidth=2)
ax.plot(fpr_gb, tpr_gb, label=f'Gradient Boosting (AUC={auc_gb:.3f})', color='#A44A4A', linewidth=2)
ax.plot([0, 1], [0, 1], 'k--', label='Random Guess')
ax.set_xlabel('False Positive Rate')
ax.set_ylabel('True Positive Rate')
ax.set_title('ROC Curve Comparison (Churn Prediction)', fontsize=14, fontweight='bold')
ax.legend(loc='lower right')
savefig('02_roc_curve.png')

importance = pd.DataFrame({'feature': feature_cols, 'importance': gb.feature_importances_})
importance = importance.sort_values('importance', ascending=True)

fig, ax = plt.subplots(figsize=(10, 6))
ax.barh(importance['feature'], importance['importance'], color='#E07A5F')
ax.set_xlabel('Importance')
ax.set_title('Feature Importance (Churn Prediction)', fontsize=14, fontweight='bold')
savefig('02_feature_importance.png')

# ========== 6. A/B 测试图表 ==========
print("\n[6/7] 生成 A/B 测试图表...")

if USE_POLARS:
    ab_df = df.with_columns((pl.col('user_id') % 2).alias('group_id'))
    ab_df = ab_df.with_columns(pl.when(pl.col('group_id') == 0).then(pl.lit('A')).otherwise(pl.lit('B')).alias('group'))
    user_ab = ab_df.group_by(['user_id', 'group']).agg(
        pl.col('behavior_type').filter(pl.col('behavior_type') == 'buy').count().alias('buy_count')
    ).with_columns((pl.col('buy_count') > 0).cast(pl.Int32).alias('is_buy'))
    summary = user_ab.group_by('group').agg([
        pl.count().alias('total_users'),
        pl.col('is_buy').sum().alias('buyers')
    ]).with_columns((pl.col('buyers') / pl.col('total_users') * 100).alias('conversion_rate'))
    groups = summary['group'].to_list()
    rates = summary['conversion_rate'].to_list()
    buyers = summary['buyers'].to_list()
    total = summary['total_users'].to_list()
else:
    df['group'] = df['user_id'].apply(lambda x: 'A' if x % 2 == 0 else 'B')
    user_ab = df.groupby(['user_id', 'group']).agg(is_buy=('behavior_type', lambda x: int((x == 'buy').any()))).reset_index()
    summary = user_ab.groupby('group').agg(total_users=('user_id', 'count'), buyers=('is_buy', 'sum')).reset_index()
    summary['conversion_rate'] = summary['buyers'] / summary['total_users'] * 100
    groups = summary['group'].tolist()
    rates = summary['conversion_rate'].tolist()
    buyers = summary['buyers'].tolist()
    total = summary['total_users'].tolist()

fig, ax = plt.subplots(figsize=(8, 6))
bars = ax.bar(groups, rates, color=['#D4A373', '#A44A4A'], width=0.5)
ax.set_ylabel('Conversion Rate (%)')
ax.set_title('A/B Test: Conversion Rate by Group', fontsize=14, fontweight='bold')
for bar, rate, b, t in zip(bars, rates, buyers, total):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(rates)*0.01,
            f'{rate:.2f}%\n({b:,}/{t:,})', ha='center', va='bottom', fontsize=11)
savefig('03_ab_test_results.png')

# ========== 7. Cohort 留存热力图 ==========
print("\n[7/7] 生成 Cohort 留存热力图...")

if USE_POLARS:
    cohort_df = df.select(['user_id', 'date']).group_by('user_id').agg(pl.col('date').min().alias('cohort_date'))
    df_cohort = df.join(cohort_df, on='user_id')
    df_cohort = df_cohort.with_columns((pl.col('date') - pl.col('cohort_date')).dt.total_days().alias('period'))
    cohort_table = df_cohort.group_by(['cohort_date', 'period']).agg(pl.col('user_id').n_unique().alias('user_count'))
    cohort_sizes = df_cohort.group_by('cohort_date').agg(pl.col('user_id').n_unique().alias('cohort_size'))
    cohort_table = cohort_table.join(cohort_sizes, on='cohort_date')
    cohort_table = cohort_table.with_columns((pl.col('user_count') / pl.col('cohort_size') * 100).alias('retention_rate'))
    cohort_pd = cohort_table.select(['cohort_date', 'period', 'retention_rate']).to_pandas()
else:
    cohort_df = df.groupby('user_id')['date'].min().reset_index().rename(columns={'date': 'cohort_date'})
    df_cohort = df.merge(cohort_df, on='user_id')
    df_cohort['period'] = (df_cohort['date'] - df_cohort['cohort_date']).dt.days
    cohort_table = df_cohort.groupby(['cohort_date', 'period'])['user_id'].nunique().reset_index(name='user_count')
    cohort_sizes = df_cohort.groupby('cohort_date')['user_id'].nunique().reset_index(name='cohort_size')
    cohort_table = cohort_table.merge(cohort_sizes, on='cohort_date')
    cohort_table['retention_rate'] = cohort_table['user_count'] / cohort_table['cohort_size'] * 100
    cohort_pd = cohort_table[['cohort_date', 'period', 'retention_rate']]

cohort_pivot = cohort_pd.pivot(index='cohort_date', columns='period', values='retention_rate')

fig, ax = plt.subplots(figsize=(12, 8))
sns.heatmap(cohort_pivot.iloc[:, :10], annot=True, fmt='.1f', cmap='YlGnBu', ax=ax, cbar_kws={'label': 'Retention Rate (%)'})
ax.set_title('Cohort Retention Heatmap (First 10 Days)', fontsize=14, fontweight='bold')
ax.set_xlabel('Days Since First Active')
ax.set_ylabel('Cohort Date')
savefig('05_cohort_heatmap.png')

print("\n" + "="*50)
print("所有图表生成完成！")
print("="*50)
files = sorted([f for f in os.listdir(IMG_DIR) if f.endswith('.png')])
for f in files:
    size = os.path.getsize(os.path.join(IMG_DIR, f)) / 1024
    print(f"  - {f} ({size:.1f} KB)")
