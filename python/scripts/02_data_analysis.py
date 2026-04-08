"""
核心数据分析函数库
==================
封装留存率、转化率、RFM分层、异常检测等常用分析函数，
供Notebook或其他脚本调用。

作者: 数据分析师求职项目
日期: 2026-06-05
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional


def calculate_retention(
    df: pd.DataFrame,
    user_col: str = "user_id",
    date_col: str = "date",
    periods: List[int] = [1, 3, 7]
) -> pd.DataFrame:
    """
    计算留存率。

    以用户首次出现日期为基准日，统计基准日后第N天仍活跃的用户占比。

    Parameters
    ----------
    df : pd.DataFrame
        用户行为数据，需包含用户ID列与日期列。
    user_col : str, default "user_id"
        用户ID列名。
    date_col : str, default "date"
        日期列名，支持 datetime 或 date 类型。
    periods : List[int], default [1, 3, 7]
        需要计算的留存周期（天）。

    Returns
    -------
    pd.DataFrame
        各基准日对应的留存率，列包括基准日及各个period的留存率。
    """
    # 确保日期格式正确
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col]).dt.date

    # 用户首次活跃日期
    first_active = df.groupby(user_col)[date_col].min().reset_index()
    first_active.columns = [user_col, "first_date"]

    # 合并后计算距首次活跃的天数差
    merged = df.merge(first_active, on=user_col)
    merged["day_diff"] = (merged[date_col] - merged["first_date"]).apply(lambda x: x.days)

    # 按基准日统计
    cohort = merged.groupby(["first_date", "day_diff"])[user_col].nunique().unstack(fill_value=0)
    cohort_size = first_active.groupby("first_date")[user_col].nunique()
    cohort = cohort.reindex(cohort_size.index)

    # 计算留存率
    retention = cohort.divide(cohort_size, axis=0)
    result = retention[[p for p in periods if p in retention.columns]].copy()
    result.insert(0, "cohort_size", cohort_size)
    result = result.reset_index()
    return result


def calculate_conversion(
    df: pd.DataFrame,
    user_col: str = "user_id",
    behavior_col: str = "behavior_type",
    stages: List[str] = ["pv", "fav", "cart", "buy"]
) -> pd.DataFrame:
    """
    计算转化漏斗。

    以独立用户为口径，统计各阶段的用户数及相对上一阶段/首阶段的转化率。

    Parameters
    ----------
    df : pd.DataFrame
        用户行为数据。
    user_col : str, default "user_id"
        用户ID列名。
    behavior_col : str, default "behavior_type"
        行为类型列名。
    stages : List[str], default ["pv", "fav", "cart", "buy"]
        漏斗阶段，按从上到下顺序传入。

    Returns
    -------
    pd.DataFrame
        包含 stage, users, conversion_to_prev, conversion_to_first 四列。
    """
    funnel: Dict[str, int] = {}
    for stage in stages:
        funnel[stage] = df[df[behavior_col] == stage][user_col].nunique()

    result = pd.DataFrame({
        "stage": stages,
        "users": [funnel[s] for s in stages]
    })

    result["conversion_to_prev"] = result["users"].pct_change().fillna(1.0) + 1
    result.loc[0, "conversion_to_prev"] = 1.0
    result["conversion_to_first"] = result["users"] / result["users"].iloc[0]
    return result


def calculate_rfm(
    df: pd.DataFrame,
    user_col: str = "user_id",
    date_col: str = "date",
    behavior_col: str = "behavior_type",
    buy_value: str = "buy",
    quantiles: List[float] = [0.33, 0.66]
) -> pd.DataFrame:
    """
    计算RFM分层。

    R (Recency): 最近一次购买距今天数（越小越好）
    F (Frequency): 购买次数（越大越好）
    M (Monetary): 由于本数据集无金额，以购买次数代替，或调用方可自行传入金额列。

    Parameters
    ----------
    df : pd.DataFrame
        用户行为数据。
    user_col : str, default "user_id"
        用户ID列名。
    date_col : str, default "date"
        日期列名。
    behavior_col : str, default "behavior_type"
        行为类型列名。
    buy_value : str, default "buy"
        代表购买行为的取值。
    quantiles : List[float], default [0.33, 0.66]
        用于分层的分位数阈值。

    Returns
    -------
    pd.DataFrame
        包含 user_id, recency, frequency, monetary, R_score, F_score, M_score, RFM_score 列。
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col]).dt.date
    max_date = df[date_col].max()

    buy_df = df[df[behavior_col] == buy_value]

    rfm = buy_df.groupby(user_col).agg(
        last_date=(date_col, "max"),
        frequency=(behavior_col, "count")
    ).reset_index()

    rfm["recency"] = (max_date - rfm["last_date"]).apply(lambda x: x.days)
    rfm["monetary"] = rfm["frequency"]  # 无金额字段时以购买频次代替

    # 打分：R越小分数越高（反向），F/M越大分数越高
    rfm["R_score"] = pd.qcut(rfm["recency"], q=[0] + quantiles + [1], labels=[3, 2, 1]).astype(int)
    rfm["F_score"] = pd.qcut(rfm["frequency"].rank(method="first"), q=[0] + quantiles + [1], labels=[1, 2, 3]).astype(int)
    rfm["M_score"] = pd.qcut(rfm["monetary"].rank(method="first"), q=[0] + quantiles + [1], labels=[1, 2, 3]).astype(int)

    rfm["RFM_score"] = rfm["R_score"].astype(str) + rfm["F_score"].astype(str) + rfm["M_score"].astype(str)
    return rfm


def detect_anomalies_3sigma(
    series: pd.Series,
    return_bounds: bool = False
) -> pd.Series:
    """
    使用3σ原则检测异常值。

    超出均值 ± 3倍标准差的值被标记为异常（True）。

    Parameters
    ----------
    series : pd.Series
        待检测的数值序列。
    return_bounds : bool, default False
        若为True，额外返回 (lower_bound, upper_bound)。

    Returns
    -------
    pd.Series 或 Tuple[pd.Series, Tuple[float, float]]
        异常标记序列；若return_bounds=True，则同时返回上下界。
    """
    mean = series.mean()
    std = series.std()
    lower = mean - 3 * std
    upper = mean + 3 * std
    anomalies = (series < lower) | (series > upper)
    if return_bounds:
        return anomalies, (lower, upper)
    return anomalies


def detect_anomalies_iqr(
    series: pd.Series,
    return_bounds: bool = False
) -> pd.Series:
    """
    使用IQR（四分位距）法检测异常值。

    超出 Q1 - 1.5*IQR 或 Q3 + 1.5*IQR 的值被标记为异常。

    Parameters
    ----------
    series : pd.Series
        待检测的数值序列。
    return_bounds : bool, default False
        若为True，额外返回 (lower_bound, upper_bound)。

    Returns
    -------
    pd.Series 或 Tuple[pd.Series, Tuple[float, float]]
        异常标记序列；若return_bounds=True，则同时返回上下界。
    """
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    anomalies = (series < lower) | (series > upper)
    if return_bounds:
        return anomalies, (lower, upper)
    return anomalies


if __name__ == "__main__":
    # 简单自测：生成模拟数据并调用各函数
    np.random.seed(0)
    n = 5000
    users = np.random.choice(range(100, 600), n)
    behaviors = np.random.choice(["pv", "buy", "cart", "fav"], n, p=[0.7, 0.05, 0.15, 0.10])
    start = datetime(2017, 11, 25)
    dates = [start + timedelta(days=int(d)) for d in np.random.randint(0, 9, n)]
    test_df = pd.DataFrame({
        "user_id": users,
        "behavior_type": behaviors,
        "date": dates
    })

    print("=== 留存率 ===")
    print(calculate_retention(test_df).head())

    print("\n=== 转化漏斗 ===")
    print(calculate_conversion(test_df))

    print("\n=== RFM分层 ===")
    print(calculate_rfm(test_df).head())

    print("\n=== 3σ异常检测（以每日PV量为例）===")
    daily_pv = test_df[test_df["behavior_type"] == "pv"].groupby("date").size()
    anomalies, bounds = detect_anomalies_3sigma(daily_pv, return_bounds=True)
    print(f"异常天数: {anomalies.sum()}, 上下界: {bounds}")
