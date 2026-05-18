import os
import streamlit as st
import polars as pl
import plotly.express as px
import plotly.graph_objects as go

# ========== 页面配置 ==========
st.set_page_config(
    page_title="电商用户行为分析平台 | 2026",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 暖色调配色 ==========
WARM_COLORS = [
    "#D4A373", "#E07A5F", "#F4A261", "#E9C46A", "#C38D9E",
    "#E8A87C", "#F2CC8F", "#BC6C25", "#A44A4A", "#DDA15E"
]

COLOR_MAP = {
    "pv": "#D4A373",
    "fav": "#E07A5F",
    "cart": "#F4A261",
    "buy": "#A44A4A"
}

# ========== 数据路径 ==========
import os

# ========== 路径配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "..", "data", "processed", "user_behavior_cleaned.csv")


# ========== 数据加载 ==========
@st.cache_data(show_spinner="正在加载数据，请稍候...")
def load_data(path: str):
    if not os.path.exists(path):
        return None
    # 使用 Polars 读取大 CSV，性能优异且内存占用低
    df = pl.read_csv(path)
    return df


# ========== 筛选逻辑 ==========
def apply_filters(df, selected_dates, selected_behaviors, hour_range, weekend_option):
    if df is None:
        return None

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


# ========== KPI 计算 ==========
def compute_kpis(df):
    total_users = df["user_id"].n_unique()
    total_pv = df.filter(pl.col("behavior_type") == "pv").shape[0]

    buy_count = df.filter(pl.col("behavior_type") == "buy").shape[0]
    pv_count = df.filter(pl.col("behavior_type") == "pv").shape[0]
    conversion_rate = buy_count / pv_count * 100 if pv_count > 0 else 0.0

    # 复购率：购买次数 >= 2 的用户 / 至少购买 1 次的用户
    buy_users = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by("user_id")
        .agg(pl.count().alias("buy_cnt"))
    )
    total_buyers = buy_users.shape[0]
    repeat_buyers = buy_users.filter(pl.col("buy_cnt") >= 2).shape[0]
    repurchase_rate = repeat_buyers / total_buyers * 100 if total_buyers > 0 else 0.0

    return total_users, total_pv, conversion_rate, repurchase_rate


# ========== 模块3: 流量趋势 ==========
def plot_dau(df):
    dau = (
        df.group_by("date")
        .agg(pl.col("user_id").n_unique().alias("DAU"))
        .sort("date")
    )
    fig = px.line(
        dau.to_pandas(),
        x="date",
        y="DAU",
        title="Daily Active Users (DAU)",
        markers=True,
        color_discrete_sequence=["#E07A5F"]
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig


def plot_behavior_trend(df):
    trend = (
        df.group_by(["date", "behavior_type"])
        .agg(pl.count().alias("count"))
        .sort(["date", "behavior_type"])
    )
    fig = px.line(
        trend.to_pandas(),
        x="date",
        y="count",
        color="behavior_type",
        title="Daily Behavior Trend",
        markers=True,
        color_discrete_map=COLOR_MAP
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig


def plot_hourly_distribution(df):
    hourly = (
        df.group_by(["hour", "behavior_type"])
        .agg(pl.count().alias("count"))
        .sort(["hour", "behavior_type"])
    )
    fig = px.bar(
        hourly.to_pandas(),
        x="hour",
        y="count",
        color="behavior_type",
        title="Hourly Behavior Distribution",
        barmode="group",
        color_discrete_map=COLOR_MAP
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig


# ========== 模块4: 转化漏斗 ==========
def plot_funnel(df):
    counts = (
        df.filter(pl.col("behavior_type").is_in(["pv", "fav", "cart", "buy"]))
        .group_by("behavior_type")
        .agg(pl.count().alias("count"))
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

    fig = go.Figure(go.Funnel(
        y=["Page View", "Favorite", "Add to Cart", "Purchase"],
        x=values,
        textposition="inside",
        textinfo="value+percent initial",
        marker=dict(
            color=["#D4A373", "#E8A87C", "#F4A261", "#A44A4A"]
        ),
        connector=dict(color="#BC6C25", dash="dot")
    ))
    fig.update_layout(
        title="Conversion Funnel (PV → Fav → Cart → Buy)",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig, values, conversion_rates


# ========== 模块5: 用户价值分析 ==========
def plot_user_activity(df):
    user_activity = df.group_by("user_id").agg(pl.count().alias("activity"))

    def count_bin(low, high, label):
        if high == float("inf"):
            cnt = user_activity.filter(pl.col("activity") > low).shape[0]
        else:
            cnt = user_activity.filter(
                (pl.col("activity") > low) & (pl.col("activity") <= high)
            ).shape[0]
        return {"activity_group": label, "user_count": cnt}

    bins = [
        (0, 10, "1-10"),
        (10, 50, "11-50"),
        (50, 100, "51-100"),
        (100, 500, "101-500"),
        (500, float("inf"), "500+")
    ]
    rows = [count_bin(low, high, label) for low, high, label in bins]
    dist = pl.DataFrame(rows)

    fig = px.bar(
        dist.to_pandas(),
        x="activity_group",
        y="user_count",
        title="User Activity Distribution (Behavior Count)",
        color_discrete_sequence=["#E07A5F"]
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig


def plot_repurchase_trend(df):
    daily_buyers = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by(["date", "user_id"])
        .agg(pl.count().alias("buy_cnt"))
    )
    daily_repurchase = (
        daily_buyers.group_by("date")
        .agg([
            pl.count().alias("total_buyers"),
            pl.col("buy_cnt").filter(pl.col("buy_cnt") >= 2).count().alias("repeat_buyers")
        ])
        .with_columns(
            (pl.col("repeat_buyers") / pl.col("total_buyers") * 100).alias("repurchase_rate")
        )
        .sort("date")
    )

    fig = px.line(
        daily_repurchase.to_pandas(),
        x="date",
        y="repurchase_rate",
        title="Daily Repurchase Rate Trend",
        markers=True,
        color_discrete_sequence=["#A44A4A"]
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig


def plot_rfm_style(df):
    user_stats = df.group_by("user_id").agg([
        pl.count().alias("frequency"),
        pl.col("behavior_type").filter(pl.col("behavior_type") == "buy").count().alias("monetary")
    ])

    def count_seg(condition, label):
        cnt = user_stats.filter(condition).shape[0]
        return {"segment": label, "count": cnt}

    segs = [
        (pl.col("monetary") == 0, "No Purchase"),
        (pl.col("monetary") == 1, "One-time Buyer"),
        ((pl.col("monetary") >= 2) & (pl.col("monetary") <= 3), "Occasional Buyer"),
        ((pl.col("monetary") >= 4) & (pl.col("monetary") <= 10), "Regular Buyer"),
        (pl.col("monetary") > 10, "VIP Buyer"),
    ]
    rows = [count_seg(cond, label) for cond, label in segs]
    seg = pl.DataFrame(rows)

    fig = px.pie(
        seg.to_pandas(),
        names="segment",
        values="count",
        title="User Value Segments (by Purchase Frequency)",
        color_discrete_sequence=WARM_COLORS[:5]
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig


# ========== 模块6: 商品分析 ==========
def plot_top_items(df):
    top_items = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by("item_id")
        .agg(pl.count().alias("buy_count"))
        .sort("buy_count", descending=True)
        .head(10)
    )
    fig = px.bar(
        top_items.to_pandas(),
        x="buy_count",
        y="item_id",
        orientation="h",
        title="Top 10 Best-Selling Items",
        color_discrete_sequence=["#F4A261"]
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig


def plot_top_categories(df):
    top_cat = (
        df.filter(pl.col("behavior_type") == "buy")
        .group_by("category_id")
        .agg(pl.count().alias("buy_count"))
        .sort("buy_count", descending=True)
        .head(10)
    )
    fig = px.bar(
        top_cat.to_pandas(),
        x="category_id",
        y="buy_count",
        title="Top 10 Best-Selling Categories",
        color_discrete_sequence=["#E8A87C"]
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig


def plot_item_scatter(df):
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
        color_discrete_sequence=["#E07A5F"]
    )
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12),
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig


# ========== 模块7: 数据探索 ==========
def show_data_explorer(df):
    st.subheader("Data Explorer (Top 1000 Rows)")
    display_df = df.head(1000)
    st.dataframe(display_df.to_pandas(), use_container_width=True)

    # 使用 pandas 生成 CSV 字符串，兼容性最好
    csv = display_df.to_pandas().to_csv(index=False)
    st.download_button(
        label="Download Displayed Data as CSV",
        data=csv,
        file_name="filtered_user_behavior_sample.csv",
        mime="text/csv"
    )


# ========== 主程序 ==========
def main():
    st.title("电商用户行为分析平台 | 2026")
    st.markdown("基于阿里云天池淘宝用户行为数据集 (2017-11-24 ~ 2017-12-03)")

    # 加载数据
    df = load_data(DATA_PATH)
    if df is None:
        st.error(f"数据文件未找到: {DATA_PATH}")
        st.info("请确认数据文件路径正确后刷新页面。")
        return

    st.sidebar.header("筛选条件")

    # 获取唯一值
    all_dates = df["date"].unique().sort().to_list()
    all_behaviors = df["behavior_type"].unique().sort().to_list()

    selected_dates = st.sidebar.multiselect("选择日期", options=all_dates, default=all_dates)
    selected_behaviors = st.sidebar.multiselect("行为类型", options=all_behaviors, default=all_behaviors)
    hour_range = st.sidebar.slider("小时范围", 0, 23, (0, 23))
    weekend_option = st.sidebar.radio("周末筛选", options=["全部", "仅周末", "仅工作日"], index=0)

    # 应用筛选
    filtered_df = apply_filters(df, selected_dates, selected_behaviors, hour_range, weekend_option)

    if filtered_df is None or filtered_df.shape[0] == 0:
        st.warning("当前筛选条件下无数据，请调整筛选器。")
        return

    # 显示数据规模
    st.sidebar.markdown("---")
    st.sidebar.metric("当前数据行数", f"{filtered_df.shape[0]:,}")

    # ========== 模块1: KPI 卡片 ==========
    st.header("核心指标")
    total_users, total_pv, conversion_rate, repurchase_rate = compute_kpis(filtered_df)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Unique Users", f"{total_users:,}")
    col2.metric("Total Page Views", f"{total_pv:,}")
    col3.metric("Purchase Conversion Rate", f"{conversion_rate:.2f}%")
    col4.metric("User Repurchase Rate", f"{repurchase_rate:.2f}%")

    st.markdown("---")

    # ========== 模块3: 流量趋势 ==========
    st.header("流量趋势分析")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(plot_dau(filtered_df), use_container_width=True)
    with c2:
        st.plotly_chart(plot_behavior_trend(filtered_df), use_container_width=True)

    st.plotly_chart(plot_hourly_distribution(filtered_df), use_container_width=True)

    st.markdown("---")

    # ========== 模块4: 转化漏斗 ==========
    st.header("转化漏斗")
    funnel_fig, funnel_values, funnel_rates = plot_funnel(filtered_df)
    st.plotly_chart(funnel_fig, use_container_width=True)

    funnel_df = pl.DataFrame({
        "Stage": ["Page View", "Favorite", "Add to Cart", "Purchase"],
        "Count": funnel_values,
        "Conversion Rate (%)": [f"{r:.2f}" for r in funnel_rates]
    })
    st.dataframe(funnel_df.to_pandas(), use_container_width=True)

    st.markdown("---")

    # ========== 模块5: 用户价值分析 ==========
    st.header("用户价值分析")
    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(plot_rfm_style(filtered_df), use_container_width=True)
    with c4:
        st.plotly_chart(plot_user_activity(filtered_df), use_container_width=True)

    st.plotly_chart(plot_repurchase_trend(filtered_df), use_container_width=True)

    st.markdown("---")

    # ========== 模块6: 商品分析 ==========
    st.header("商品分析")
    c5, c6 = st.columns(2)
    with c5:
        st.plotly_chart(plot_top_items(filtered_df), use_container_width=True)
    with c6:
        st.plotly_chart(plot_top_categories(filtered_df), use_container_width=True)

    st.plotly_chart(plot_item_scatter(filtered_df), use_container_width=True)

    st.markdown("---")

    # ========== 模块7: 数据探索 ==========
    st.header("数据探索")
    show_data_explorer(filtered_df)

    st.markdown("---")
    st.caption("Dashboard built with Streamlit & Plotly | Data Analyst Project 2026")


if __name__ == "__main__":
    main()
