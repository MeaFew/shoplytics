"""Shared user-behavior aggregation helpers for shoplytics.

The `pl.col("behavior_type").filter(... == X).count().alias(...)` block was
copy-pasted across churn_prediction.py, recommendation.py, ab_testing.py, and
dashboard/app.py. Centralize it here so the behaviour set is defined once.
"""

import polars as pl

BEHAVIORS = ("pv", "buy", "cart", "fav")


def behavior_counts(df: pl.DataFrame, behaviors=BEHAVIORS) -> pl.DataFrame:
    """Per-user counts of each behaviour type.

    Returns a frame with columns ``user_id, total_pv, total_buy, total_cart,
    total_fav``. Callers can join additional features onto this.
    """
    return df.group_by("user_id").agg(
        [
            pl.col("behavior_type")
            .filter(pl.col("behavior_type") == b)
            .count()
            .alias(f"total_{b}")
            for b in behaviors
        ]
    )
