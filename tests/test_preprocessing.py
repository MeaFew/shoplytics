"""
Tests for data preprocessing pipeline
=====================================
Run: pytest tests/ -v
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
import pytest
from config import CLEANED_CSV_PATH


@pytest.fixture(scope="module")
def cleaned_df():
    """Module-scoped fixture: reads the cleaned CSV once for all tests."""
    return pd.read_csv(CLEANED_CSV_PATH)


def test_cleaned_data_exists():
    """清洗后的数据文件必须存在。"""
    assert CLEANED_CSV_PATH.exists(), f"Cleaned data not found at {CLEANED_CSV_PATH}"


def test_cleaned_data_columns(cleaned_df):
    """清洗后的数据必须包含预期的列。"""
    expected_cols = {'user_id', 'item_id', 'category_id', 'behavior_type', 'timestamp', 'date'}
    assert expected_cols.issubset(set(cleaned_df.columns)), \
        f"Missing columns: {expected_cols - set(cleaned_df.columns)}"


def test_behavior_types_valid(cleaned_df):
    """behavior_type 必须是限定值之一。"""
    valid_behaviors = {'pv', 'buy', 'cart', 'fav'}
    assert set(cleaned_df['behavior_type'].unique()).issubset(valid_behaviors), \
        f"Invalid behavior types: {set(cleaned_df['behavior_type'].unique()) - valid_behaviors}"


def test_timestamps_positive(cleaned_df):
    """timestamp 必须为正数。"""
    assert (cleaned_df['timestamp'] > 0).all(), "Found non-positive timestamps"


def test_ids_positive(cleaned_df):
    """user_id, item_id, category_id 必须为正数。"""
    for col in ['user_id', 'item_id', 'category_id']:
        assert (cleaned_df[col] > 0).all(), f"Found non-positive {col}"
