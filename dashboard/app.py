"""
改进版 Streamlit Dashboard
改进点：
1. 使用 config.py 管理路径
2. 优先读取 Parquet，保留数据类型
3. 修复 RFM 命名（实际为 F+M，重命名为 Purchase Segments）
4. 添加数据加载异常处理和用户友好的错误提示
5. KPI 计算优化（减少重复过滤）
6. 活动分箱逻辑修复（包含边界情况）
7. 添加缓存刷新按钮
"""

import logging
import os
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st

from config import CLEANED_CSV_PATH, CLEANED_PARQUET_PATH

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

# ---------------------------------------------------------------------------
# 页面配置
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="电商用户行为分析平台 | E-Commerce Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

WARM_COLORS = [
    "#D4A373", "#E07A5F", "#F4A261", "#E9C46A", "#C38D9E",
    "#E8A87C", "#F2CC8F", "#BC6C25", "#A44A4A", "#DDA15E",
]

COLOR_MAP = {
    "pv": "#D4A373",
    "fav": "#E07A5F",
    "cart": "#F4A261",
    "buy": "#A44A4A",
}

# ---------------------------------------------------------------------------
# 数据加载（优先 Parquet）
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="正在加载数据，请稍候...")
def load_data(csv_path: Path, parquet_path: Path) -> pl.DataFrame | None:
    """优先加载 Parquet（保留类型、速度更快），回退到 CSV。"""
    try:
        if parquet_path.exists():
            logger.info(f"Loading Parquet: {parquet_path}")
            return pl.read_parquet(parquet_path)
        elif csv_path.exists():
            logger.info(f"Loading CSV: {csv_path}")
            df = pl.read_csv(csv_path)
            # 修复可能的类型问题
            if df.schema.get("date") == pl.Utf8:
                df = df.with_columns(pl.col("date").str.to_date())
            return df
        else:
            return None
    except Exception as e:
        logger.error(f"数据加载失败: {e}")
        return None


# ---------------------------------------------------------------------------
# 筛选逻辑
# ---------------------------------------------------------------------------
def apply_filters(
    df: pl.DataFrame,
    selected_dates: list,
    selected_behaviors: list,
    hour_range: tuple,
    weekend_option: str,
) -> pl.DataFrame:
    if df is None:
        raise ValueError("DataFrame is None")

    mask = pl.lit(True)
    if selected_dates:
        mask = mask & pl.col("date").is_in(selected_dates)
    if selected_behaviors:
        mask = mask & pl.col("behavior_type").is_in(selected_behaviors)
    mask = mask & pl.col("hour").is_between(hour_range[0], hour_range[1])
    if weekend_option == "仅周末":
        mask = mask & (pl.col("is_weekend") == 1)
    elif weekend_option == "仅工作日":
        mask = mask & (pl.col("is_weekend") == 0)

    return df.filter(mask)


# ---------------------------------------------------------------------------
# KPI 计算（优化版：单次聚合减少重复过滤）
# ---------------------------------------------------------------------------
def compute_kpis(df: pl.DataFrame) -> tuple:
    total_users = df["user_id"].n_unique()

    # 一次性统计所有行为数量
    behavior_counts = (
        df.group_by("behavior_type")
        .agg(pl.len().alias("count"))
    )
    counts = {
        row["behavior_type"]: row["count"]
        for row in behavior_counts.iter_rows(named=True)
    }

    total_pv = counts.get("pv", 0)
    total_buy = counts.get("buy", 0)
    conversion_rate = total_buy / total_pv * 100 if total_pv > 0 else 0.0

    # 复购率
    buy_users = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by("user_id")
        .agg(pl.count().alias("buy_cnt"))
    )
    total_buyers = buy_users.shape[0]
    repeat_buyers = buy_users.filter(pl.col("buy_cnt") >= 2).shape[0]
    repurchase_rate = repeat_buyers / total_buyers * 100 if total_buyers > 0 else 0.0

    return total_users, total_pv, conversion_rate, repurchase_rate


# ---------------------------------------------------------------------------
# 图表模块
# ---------------------------------------------------------------------------
def plot_dau(df: pl.DataFrame) -> go.Figure:
    dau = (
        df.group_by("date")
        .agg(pl.col("user_id").n_unique().alias("DAU"))
        .sort("date")
        .to_pandas()
    )
    fig = px.line(
        dau,
        x="date",
        y="DAU",
        title="Daily Active Users (DAU)",
        markers=True,
        color_discrete_sequence=["#E07A5F"],
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


def plot_behavior_trend(df: pl.DataFrame) -> go.Figure:
    trend = (
        df.group_by(["date", "behavior_type"])
        .agg(pl.len().alias("count"))
        .sort(["date", "behavior_type"])
        .to_pandas()
    )
    fig = px.line(
        trend,
        x="date",
        y="count",
        color="behavior_type",
        title="Daily Behavior Trend",
        markers=True,
        color_discrete_map=COLOR_MAP,
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def plot_hourly_distribution(df: pl.DataFrame) -> go.Figure:
    hourly = (
        df.group_by(["hour", "behavior_type"])
        .agg(pl.len().alias("count"))
        .sort(["hour", "behavior_type"])
        .to_pandas()
    )
    fig = px.bar(
        hourly,
        x="hour",
        y="count",
        color="behavior_type",
        title="Hourly Behavior Distribution",
        barmode="group",
        color_discrete_map=COLOR_MAP,
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def plot_funnel(df: pl.DataFrame) -> tuple:
    counts = (
        df.filter(pl.col("behavior_type").is_in(["pv", "fav", "cart", "buy"]))
        .group_by("behavior_type")
        .agg(pl.len().alias("count"))
    )
    behavior_order = ["pv", "fav", "cart", "buy"]
    counts_dict = {row[0]: row[1] for row in counts.iter_rows()}
    values = [counts_dict.get(b, 0) for b in behavior_order]

    conversion_rates = []
    for i, v in enumerate(values):
        if i == 0:
            conversion_rates.append(100.0)
        else:
            prev = values[i - 1]
            rate = v / prev * 100 if prev > 0 else 0.0
            conversion_rates.append(rate)

    fig = go.Figure(
        go.Funnel(
            y=["Page View", "Favorite", "Add to Cart", "Purchase"],
            x=values,
            textposition="inside",
            textinfo="value+percent initial",
            marker=dict(color=["#D4A373", "#E8A87C", "#F4A261", "#A44A4A"]),
            connector=dict(color="#BC6C25", dash="dot"),
        )
    )
    fig.update_layout(
        title="Conversion Funnel (PV → Fav → Cart → Buy)",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig, values, conversion_rates


# ---------------------------------------------------------------------------
# 修复版用户活动分箱（包含边界情况）
# ---------------------------------------------------------------------------
def plot_user_activity(df: pl.DataFrame) -> go.Figure:
    user_activity = df.group_by("user_id").agg(pl.len().alias("activity"))

    # 修复：使用左闭右开区间，确保覆盖 0 的情况
    bins = [
        (0, 10, "1-10"),
        (11, 50, "11-50"),
        (51, 100, "51-100"),
        (101, 500, "101-500"),
        (501, float("inf"), "500+"),
    ]

    rows = []
    for low, high, label in bins:
        if high == float("inf"):
            cnt = user_activity.filter(pl.col("activity") >= low).shape[0]
        else:
            cnt = user_activity.filter(
                (pl.col("activity") >= low) & (pl.col("activity") <= high)
            ).shape[0]
        rows.append({"activity_group": label, "user_count": cnt})

    dist = pl.DataFrame(rows)

    fig = px.bar(
        dist.to_pandas(),
        x="activity_group",
        y="user_count",
        title="User Activity Distribution (Behavior Count)",
        color_discrete_sequence=["#E07A5F"],
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


def plot_repurchase_trend(df: pl.DataFrame) -> go.Figure:
    daily_buyers = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by(["date", "user_id"])
        .agg(pl.count().alias("buy_cnt"))
    )
    daily_repurchase = (
        daily_buyers.group_by("date")
        .agg([
            pl.count().alias("total_buyers"),
            pl.col("buy_cnt").filter(pl.col("buy_cnt") >= 2).count().alias("repeat_buyers"),
        ])
        .with_columns(
            (pl.col("repeat_buyers") / pl.col("total_buyers") * 100).alias("repurchase_rate")
        )
        .sort("date")
        .to_pandas()
    )

    fig = px.line(
        daily_repurchase,
        x="date",
        y="repurchase_rate",
        title="Daily Repurchase Rate Trend",
        markers=True,
        color_discrete_sequence=["#A44A4A"],
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


# ---------------------------------------------------------------------------
# 修复命名：Purchase Segments（原错误命名为 RFM）
# ---------------------------------------------------------------------------
def plot_purchase_segments(df: pl.DataFrame) -> go.Figure:
    """按购买频次划分用户价值段（注意：这不是完整的 RFM，缺少 Recency）。"""
    user_stats = df.group_by("user_id").agg([
        pl.count().alias("frequency"),
        pl.col("behavior_type").filter(pl.col("behavior_type") == "buy").count().alias("purchase_count"),
    ])

    segs = [
        (pl.col("purchase_count") == 0, "No Purchase"),
        (pl.col("purchase_count") == 1, "One-time Buyer"),
        ((pl.col("purchase_count") >= 2) & (pl.col("purchase_count") <= 3), "Occasional Buyer"),
        ((pl.col("purchase_count") >= 4) & (pl.col("purchase_count") <= 10), "Regular Buyer"),
        (pl.col("purchase_count") > 10, "VIP Buyer"),
    ]
    rows = []
    for condition, label in segs:
        cnt = user_stats.filter(condition).shape[0]
        rows.append({"segment": label, "count": cnt})

    seg = pl.DataFrame(rows)

    fig = px.pie(
        seg.to_pandas(),
        names="segment",
        values="count",
        title="User Purchase Segments (by Purchase Frequency)",
        color_discrete_sequence=WARM_COLORS[:5],
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


# ---------------------------------------------------------------------------
# 商品分析
# ---------------------------------------------------------------------------
def plot_top_items(df: pl.DataFrame) -> go.Figure:
    top_items = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by("item_id")
        .agg(pl.count().alias("buy_count"))
        .sort("buy_count", descending=True)
        .head(10)
        .to_pandas()
    )
    fig = px.bar(
        top_items,
        x="buy_count",
        y="item_id",
        orientation="h",
        title="Top 10 Best-Selling Items",
        color_discrete_sequence=["#F4A261"],
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


def plot_top_categories(df: pl.DataFrame) -> go.Figure:
    top_cat = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by("category_id")
        .agg(pl.count().alias("buy_count"))
        .sort("buy_count", descending=True)
        .head(10)
        .to_pandas()
    )
    fig = px.bar(
        top_cat,
        x="category_id",
        y="buy_count",
        title="Top 10 Best-Selling Categories",
        color_discrete_sequence=["#E8A87C"],
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


def plot_item_scatter(df: pl.DataFrame) -> go.Figure:
    pv_df = (
        df.filter(pl.col("behavior_type") == "pv")
        .group_by("item_id")
        .agg(pl.count().alias("pv_count"))
    )
    buy_df = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by("item_id")
        .agg(pl.count().alias("buy_count"))
    )
    item_stats = pv_df.join(buy_df, on="item_id", how="left").fill_null(0)
    item_stats = item_stats.filter(pl.col("pv_count") > 0)

    if item_stats.shape[0] > 5000:
        item_stats = item_stats.sample(n=5000, seed=42)

    fig = px.scatter(
        item_stats.to_pandas(),
        x="pv_count",
        y="buy_count",
        title="Item Conversion Efficiency (PV vs Buy)",
        opacity=0.6,
        color_discrete_sequence=["#E07A5F"],
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


# ---------------------------------------------------------------------------
# 数据探索
# ---------------------------------------------------------------------------
def show_data_explorer(df: pl.DataFrame) -> None:
    st.subheader("Data Explorer (Top 1000 Rows)")
    # 使用 Polars 的 head 然后转 pandas，减少内存
    display_df = df.head(1000).to_pandas()
    st.dataframe(display_df, use_container_width=True)

    csv = display_df.to_csv(index=False)
    st.download_button(
        label="Download Displayed Data as CSV",
        data=csv,
        file_name="filtered_user_behavior_sample.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------
def main():
    st.title("电商用户行为分析平台 | E-Commerce Analytics")
    st.markdown("基于阿里云天池淘宝用户行为数据集 (2017-11-24 ~ 2017-12-03)")

    # 加载数据
    df = load_data(CLEANED_CSV_PATH, CLEANED_PARQUET_PATH)

    if df is None:
        st.error("❌ 数据文件未找到")
        st.info(
            f"请确认以下路径之一存在数据文件：\n\n"
            f"- Parquet: `{CLEANED_PARQUET_PATH}`\n"
            f"- CSV: `{CLEANED_CSV_PATH}`\n\n"
            f"请先运行预处理脚本生成数据。"
        )
        return

    # 侧边栏筛选
    st.sidebar.header("筛选条件")

    all_dates = df["date"].unique().sort().to_list()
    all_behaviors = df["behavior_type"].unique().sort().to_list()

    selected_dates = st.sidebar.multiselect("选择日期", options=all_dates, default=all_dates)
    selected_behaviors = st.sidebar.multiselect("行为类型", options=all_behaviors, default=all_behaviors)
    hour_range = st.sidebar.slider("小时范围", 0, 23, (0, 23))
    weekend_option = st.sidebar.radio("周末筛选", options=["全部", "仅周末", "仅工作日"], index=0)

    # 刷新缓存按钮
    if st.sidebar.button("🔄 刷新数据缓存"):
        st.cache_data.clear()
        st.rerun()

    # 应用筛选
    try:
        filtered_df = apply_filters(df, selected_dates, selected_behaviors, hour_range, weekend_option)
    except Exception as e:
        st.error(f"筛选时发生错误: {e}")
        return

    if filtered_df is None or filtered_df.shape[0] == 0:
        st.warning("当前筛选条件下无数据，请调整筛选器。")
        return

    st.sidebar.markdown("---")
    st.sidebar.metric("当前数据行数", f"{filtered_df.shape[0]:,}")

    # ========== KPI 卡片 ==========
    st.header("核心指标")
    total_users, total_pv, conversion_rate, repurchase_rate = compute_kpis(filtered_df)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Unique Users", f"{total_users:,}")
    col2.metric("Total Page Views", f"{total_pv:,}")
    col3.metric("Purchase Conversion Rate", f"{conversion_rate:.2f}%")
    col4.metric("User Repurchase Rate", f"{repurchase_rate:.2f}%")

    st.markdown("---")

    # ========== 流量趋势 ==========
    st.header("流量趋势分析")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(plot_dau(filtered_df), use_container_width=True)
    with c2:
        st.plotly_chart(plot_behavior_trend(filtered_df), use_container_width=True)

    st.plotly_chart(plot_hourly_distribution(filtered_df), use_container_width=True)
    st.markdown("---")

    # ========== 转化漏斗 ==========
    st.header("转化漏斗")
    funnel_fig, funnel_values, funnel_rates = plot_funnel(filtered_df)
    st.plotly_chart(funnel_fig, use_container_width=True)

    funnel_df = pl.DataFrame({
        "Stage": ["Page View", "Favorite", "Add to Cart", "Purchase"],
        "Count": funnel_values,
        "Conversion Rate (%)": [f"{r:.2f}" for r in funnel_rates],
    })
    st.dataframe(funnel_df.to_pandas(), use_container_width=True)
    st.markdown("---")

    # ========== 用户价值分析 ==========
    st.header("用户价值分析")
    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(plot_purchase_segments(filtered_df), use_container_width=True)
    with c4:
        st.plotly_chart(plot_user_activity(filtered_df), use_container_width=True)

    st.plotly_chart(plot_repurchase_trend(filtered_df), use_container_width=True)
    st.markdown("---")

    # ========== 商品分析 ==========
    st.header("商品分析")
    c5, c6 = st.columns(2)
    with c5:
        st.plotly_chart(plot_top_items(filtered_df), use_container_width=True)
    with c6:
        st.plotly_chart(plot_top_categories(filtered_df), use_container_width=True)

    st.plotly_chart(plot_item_scatter(filtered_df), use_container_width=True)
    st.markdown("---")

    # ========== 数据探索 ==========
    st.header("数据探索")
    show_data_explorer(filtered_df)

    st.markdown("---")
    st.caption("Dashboard built with Streamlit & Plotly | Improved Version")


if __name__ == "__main__":
    main()
