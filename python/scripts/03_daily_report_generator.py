"""
日常监控报表自动生成脚本
==========================
读取清洗后用户行为数据，计算核心KPI，生成HTML日报。
异常指标自动标红。

输出路径: ../reports/daily_report.html
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # 无GUI环境
import matplotlib.pyplot as plt
import seaborn as sns
import os
import base64
import io
from datetime import datetime, timedelta

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style('whitegrid')

# 路径配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, 'data', 'processed', 'user_behavior_cleaned.csv')
REPORT_PATH = os.path.join(BASE_DIR, 'reports', 'daily_report.html')
IMG_DIR = os.path.join(BASE_DIR, 'images')
os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)


def load_or_generate_data() -> pd.DataFrame:
    """加载真实数据；若不存在则生成模拟数据。"""
    if os.path.exists(DATA_PATH):
        df = pd.read_csv(DATA_PATH, parse_dates=['datetime', 'date'])
        print(f"[INFO] 已加载真实数据: {DATA_PATH}")
    else:
        print(f"[WARN] 数据文件不存在，生成模拟数据...")
        np.random.seed(42)
        n = 100000
        users = np.random.choice(range(1000, 9000), n)
        items = np.random.choice(range(100000, 900000), n)
        cates = np.random.choice(range(100, 1200), n)
        behaviors = np.random.choice(['pv', 'buy', 'cart', 'fav'], n, p=[0.70, 0.05, 0.15, 0.10])
        start = datetime(2017, 11, 25)
        deltas = np.random.randint(0, 9 * 24 * 3600, n)
        datetimes = [start + timedelta(seconds=int(s)) for s in deltas]
        df = pd.DataFrame({
            'user_id': users,
            'item_id': items,
            'category_id': cates,
            'behavior_type': behaviors,
            'timestamp': [int(d.timestamp()) for d in datetimes],
            'datetime': datetimes,
        })
        df['date'] = df['datetime'].dt.date
        df['hour'] = df['datetime'].dt.hour
        df['day_of_week'] = df['datetime'].dt.dayofweek
        df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)

        def time_period(h):
            if 0 <= h < 6:
                return '凌晨'
            elif 6 <= h < 12:
                return '上午'
            elif 12 <= h < 18:
                return '下午'
            else:
                return '晚上'
        df['time_period'] = df['hour'].apply(time_period)
    return df


def calculate_kpis(df: pd.DataFrame) -> dict:
    """计算核心KPI指标。"""
    df['date'] = pd.to_datetime(df['date']).dt.date
    max_date = df['date'].max()
    prev_date = max_date - timedelta(days=1)

    # 当日数据
    today_df = df[df['date'] == max_date]
    prev_df = df[df['date'] == prev_date]

    dau = today_df['user_id'].nunique()
    dau_prev = prev_df['user_id'].nunique() if len(prev_df) > 0 else dau

    pv = len(today_df[today_df['behavior_type'] == 'pv'])
    pv_prev = len(prev_df[prev_df['behavior_type'] == 'pv']) if len(prev_df) > 0 else pv

    buys = len(today_df[today_df['behavior_type'] == 'buy'])
    buys_prev = len(prev_df[prev_df['behavior_type'] == 'buy']) if len(prev_df) > 0 else buys

    # 转化率（购买用户数 / 总活跃用户数）
    buyers = today_df[today_df['behavior_type'] == 'buy']['user_id'].nunique()
    conversion = buyers / dau if dau > 0 else 0.0
    buyers_prev = prev_df[prev_df['behavior_type'] == 'buy']['user_id'].nunique() if len(prev_df) > 0 else 0
    conversion_prev = buyers_prev / dau_prev if dau_prev > 0 else conversion

    # 留存率（次日留存：今天活跃的用户中，昨天也活跃的比例）
    today_users = set(today_df['user_id'].unique())
    prev_users = set(prev_df['user_id'].unique()) if len(prev_df) > 0 else today_users
    retention = len(today_users & prev_users) / len(prev_users) if prev_users else 1.0

    kpis = {
        'report_date': str(max_date),
        'dau': dau,
        'dau_prev': dau_prev,
        'dau_change': (dau - dau_prev) / dau_prev if dau_prev else 0,
        'pv': pv,
        'pv_prev': pv_prev,
        'pv_change': (pv - pv_prev) / pv_prev if pv_prev else 0,
        'buys': buys,
        'buys_prev': buys_prev,
        'buys_change': (buys - buys_prev) / buys_prev if buys_prev else 0,
        'conversion': conversion,
        'conversion_prev': conversion_prev,
        'conversion_change': (conversion - conversion_prev) / conversion_prev if conversion_prev else 0,
        'retention': retention,
    }
    return kpis


def is_anomaly(change: float, threshold: float = 0.20) -> bool:
    """判断环比变化是否异常（超过阈值则标红）。"""
    return abs(change) > threshold


def fig_to_base64(fig) -> str:
    """将matplotlib Figure转为base64编码的PNG字符串。"""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    buf.close()
    plt.close(fig)
    return img_base64


def generate_charts(df: pd.DataFrame) -> dict:
    """生成日报所需图表，返回 {chart_name: base64_str}。"""
    charts = {}
    df['date'] = pd.to_datetime(df['date']).dt.date

    # 1. DAU趋势（最近7天）
    max_date = df['date'].max()
    recent_dates = [max_date - timedelta(days=i) for i in range(6, -1, -1)]
    dau_series = []
    for d in recent_dates:
        dau = df[df['date'] == d]['user_id'].nunique()
        dau_series.append(dau)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot([str(d) for d in recent_dates], dau_series, marker='o', color='steelblue')
    ax.set_title('近7日 DAU 趋势')
    ax.set_ylabel('活跃用户数')
    charts['dau_trend'] = fig_to_base64(fig)

    # 2. 行为分布饼图
    behavior_counts = df[df['date'] == max_date]['behavior_type'].value_counts()
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(behavior_counts, labels=behavior_counts.index, autopct='%1.1f%%', startangle=140)
    ax.set_title(f'{max_date} 行为分布')
    charts['behavior_pie'] = fig_to_base64(fig)

    # 3. 小时分布柱状图
    hourly = df[df['date'] == max_date].groupby('hour').size().reset_index(name='count')
    fig, ax = plt.subplots(figsize=(8, 4))
    sns.barplot(data=hourly, x='hour', y='count', palette='viridis', ax=ax)
    ax.set_title(f'{max_date} 小时行为分布')
    charts['hourly_bar'] = fig_to_base64(fig)

    return charts


def generate_html(kpis: dict, charts: dict) -> str:
    """组装HTML日报。"""
    def fmt_pct(v: float) -> str:
        return f"{v*100:+.1f}%"

    def style_change(v: float) -> str:
        if is_anomaly(v):
            return f'<span style="color:red;font-weight:bold;">{fmt_pct(v)} ⚠</span>'
        return f'<span style="color:green;">{fmt_pct(v)}</span>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>用户行为数据日报 - {kpis['report_date']}</title>
    <style>
        body {{ font-family: "Microsoft YaHei", SimHei, sans-serif; margin: 40px; background: #f5f6fa; }}
        .container {{ max-width: 960px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; margin-top: 20px; }}
        .kpi-card {{ background: #ecf0f1; padding: 20px; border-radius: 6px; text-align: center; }}
        .kpi-value {{ font-size: 28px; font-weight: bold; color: #2980b9; }}
        .kpi-label {{ font-size: 14px; color: #7f8c8d; margin-top: 8px; }}
        .kpi-change {{ font-size: 13px; margin-top: 6px; }}
        .chart {{ margin-top: 20px; text-align: center; }}
        .chart img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 4px; }}
        .footer {{ margin-top: 40px; font-size: 12px; color: #95a5a6; text-align: center; }}
        .alert {{ background: #ffeaa7; border-left: 4px solid #fdcb6e; padding: 10px 15px; margin-top: 20px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 用户行为数据日报</h1>
        <p>报表日期：<strong>{kpis['report_date']}</strong> | 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <h2>核心 KPI</h2>
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-value">{kpis['dau']:,}</div>
                <div class="kpi-label">DAU（日活跃用户）</div>
                <div class="kpi-change">环比 {style_change(kpis['dau_change'])}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{kpis['pv']:,}</div>
                <div class="kpi-label">PV（点击量）</div>
                <div class="kpi-change">环比 {style_change(kpis['pv_change'])}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{kpis['buys']:,}</div>
                <div class="kpi-label">购买量</div>
                <div class="kpi-change">环比 {style_change(kpis['buys_change'])}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{kpis['conversion']*100:.2f}%</div>
                <div class="kpi-label">转化率</div>
                <div class="kpi-change">环比 {style_change(kpis['conversion_change'])}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">{kpis['retention']*100:.1f}%</div>
                <div class="kpi-label">次日留存率</div>
                <div class="kpi-change">—</div>
            </div>
        </div>

        {"<div class='alert'>⚠️ 检测到异常指标（环比波动超过 ±20%），请关注标红数据。</div>" if any(is_anomaly(kpis[k]) for k in ['dau_change','pv_change','buys_change','conversion_change']) else ""}

        <h2>趋势图表</h2>
        <div class="chart">
            <h3>近7日 DAU 趋势</h3>
            <img src="data:image/png;base64,{charts.get('dau_trend', '')}" alt="DAU趋势">
        </div>
        <div class="chart">
            <h3>今日行为分布</h3>
            <img src="data:image/png;base64,{charts.get('behavior_pie', '')}" alt="行为分布">
        </div>
        <div class="chart">
            <h3>今日小时分布</h3>
            <img src="data:image/png;base64,{charts.get('hourly_bar', '')}" alt="小时分布">
        </div>

        <div class="footer">
            本报表由 python/scripts/03_daily_report_generator.py 自动生成 | 数据来源：user_behavior_cleaned.csv
        </div>
    </div>
</body>
</html>"""
    return html


def main():
    """主入口：加载数据、计算KPI、生成图表、输出HTML。"""
    print("[INFO] 开始生成日报...")
    df = load_or_generate_data()
    kpis = calculate_kpis(df)
    charts = generate_charts(df)
    html = generate_html(kpis, charts)

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"[INFO] 日报已生成: {REPORT_PATH}")
    print(f"[INFO] KPI摘要: DAU={kpis['dau']}, PV={kpis['pv']}, 购买={kpis['buys']}, 转化率={kpis['conversion']*100:.2f}%, 留存={kpis['retention']*100:.1f}%")


if __name__ == "__main__":
    main()
