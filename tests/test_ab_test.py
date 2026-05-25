"""
Tests for A/B test statistical functions
========================================
Run: pytest tests/ -v
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import numpy as np
from scipy import stats


def test_two_proportion_ztest_known_input():
    """验证两比例 Z-test 在已知输入下的输出。"""
    # 对照组: 1000 PV, 50 buy -> 5%
    # 实验组: 1000 PV, 70 buy -> 7%
    n1, x1 = 1000, 50
    n2, x2 = 1000, 70
    p1 = x1 / n1
    p2 = x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    # 与 scipy 内置函数交叉验证
    _, p_scipy = stats.proportions_ztest([x2, x1], [n2, n1])
    assert abs(p_value - p_scipy) < 1e-6, "Z-test p-value mismatch with scipy"
    assert p_value < 0.05, "Expected significant difference for 5% vs 7%"


def test_cohens_h_calculation():
    """验证 Cohen's h 效应量计算。"""
    p1, p2 = 0.05, 0.07
    h = 2 * (np.arcsin(np.sqrt(p2)) - np.arcsin(np.sqrt(p1)))
    # 预期值约为 0.089
    assert abs(h - 0.089) < 0.01, f"Cohen's h unexpected: {h}"


def test_srm_check_balanced():
    """样本比例失衡检查：平衡分组应通过。"""
    n_control = 5000
    n_treatment = 5000
    total = n_control + n_treatment
    expected_ratio = 0.5
    observed_ratio = n_treatment / total
    chi2 = ((n_treatment - total * expected_ratio) ** 2) / (total * expected_ratio) + \
           ((n_control - total * expected_ratio) ** 2) / (total * (1 - expected_ratio))
    p_value = 1 - stats.chi2.cdf(chi2, df=1)
    assert p_value > 0.01, "Balanced split should pass SRM check"


def test_srm_check_imbalanced():
    """样本比例失衡检查：严重失衡应不通过。"""
    n_control = 6000
    n_treatment = 4000
    total = n_control + n_treatment
    expected_ratio = 0.5
    chi2 = ((n_treatment - total * expected_ratio) ** 2) / (total * expected_ratio) + \
           ((n_control - total * expected_ratio) ** 2) / (total * (1 - expected_ratio))
    p_value = 1 - stats.chi2.cdf(chi2, df=1)
    assert p_value < 0.01, "Severely imbalanced split should fail SRM check"
