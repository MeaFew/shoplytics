"""
Tests for data validation script
================================
Run: pytest tests/test_validate_data.py -v
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import polars as pl

from config import CLEANED_CSV_PATH
from scripts.validate_data import validate, EXPECTED_COLUMNS


def test_validate_data_passes_on_cleaned_data():
    """清洗后的数据应通过所有校验规则."""
    if not CLEANED_CSV_PATH.exists():
        # 如果本地没有清洗数据, 跳过该测试
        import pytest
        pytest.skip(f"Cleaned data not found at {CLEANED_CSV_PATH}")

    errors = validate(CLEANED_CSV_PATH)
    assert errors == [], f"数据校验失败: {errors}"


def test_validate_detects_missing_columns(tmp_path):
    """缺少关键列时应报错."""
    csv_path = tmp_path / "bad.csv"
    df = pl.DataFrame({"user_id": [1, 2], "item_id": [10, 20]})
    df.write_csv(csv_path)

    errors = validate(csv_path)
    assert any("缺少列" in err for err in errors)


def test_validate_detects_unknown_behavior(tmp_path):
    """未知行为类型时应报错."""
    csv_path = tmp_path / "bad_behavior.csv"
    data = {col: [] for col in EXPECTED_COLUMNS.keys()}
    # 手动填充最小数据以通过空值检查
    data["user_id"] = [1]
    data["item_id"] = [1]
    data["category_id"] = [1]
    data["behavior_type"] = ["click"]  # 未知类型
    data["timestamp"] = [1511539200]
    data["date"] = ["2017-11-25"]
    data["hour"] = [0]
    data["day_of_week"] = [5]
    data["is_weekend"] = [1]
    data["time_period"] = ["dawn"]

    df = pl.DataFrame(data)
    df.write_csv(csv_path)

    errors = validate(csv_path)
    assert any("未知行为类型" in err for err in errors)
