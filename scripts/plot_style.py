"""Shared matplotlib/seaborn chart styling for shoplytics.

Several plotting scripts (ab_testing, churn_prediction, eda, recommendation)
previously repeated the same rcParams + set_style block. Importing
``apply_chart_style()`` keeps the look consistent and removes the duplication.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns


def apply_chart_style() -> None:
    """Apply the project's standard chart styling (CJK font + whitegrid)."""
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    sns.set_style("whitegrid")
