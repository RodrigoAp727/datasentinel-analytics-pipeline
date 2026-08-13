from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from validation.quality_checker import DataQualityChecker


def _write_rules(tmp_path: Path) -> Path:
    rules_file = tmp_path / "quality_rules.yaml"
    rules_file.write_text(
        "\n".join(
            [
                "required_columns:",
                "  - id",
                "  - value",
                "  - category",
                "",
                "null_threshold: 0.2",
                "duplicate_ratio_threshold: 0.0",
                "",
                "expected_types:",
                "  id: int",
                "  value: float",
                "  category: string",
                "",
                "outlier_detection:",
                "  method: iqr",
                "  max_outlier_ratio: 0.1",
                "  columns:",
                "    - value",
            ]
        ),
        encoding="utf-8",
    )
    return rules_file


def test_run_all_checks_with_clean_dataframe_passes(tmp_path: Path) -> None:
    rules_path = _write_rules(tmp_path)
    df_clean = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "value": [10.0, 11.0, 12.0, 13.0, 14.0],
            "category": ["A", "B", "C", "D", "E"],
        }
    )

    checker = DataQualityChecker(df_clean, rules_path=rules_path)
    report = checker.run_all_checks()

    assert report.status == "PASS"
    assert report.score == 100.0
    assert report.issues == []


def test_required_columns_missing_fails(tmp_path: Path) -> None:
    rules_path = _write_rules(tmp_path)
    df_missing = pd.DataFrame({"id": [1], "value": [1.0]})

    checker = DataQualityChecker(df_missing, rules_path=rules_path)
    report = checker.run_all_checks()

    assert report.status == "FAIL"
    assert any(issue.check == "required_columns" for issue in report.issues)


def test_null_threshold_warning(tmp_path: Path) -> None:
    rules_path = _write_rules(tmp_path)
    df_nulls = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "value": [10.0, None, None, 13.0, 14.0],
            "category": ["A", "B", "C", "D", "E"],
        }
    )

    checker = DataQualityChecker(df_nulls, rules_path=rules_path)
    report = checker.run_all_checks()

    assert any(issue.check == "null_threshold" for issue in report.issues)
    assert report.status in {"WARNING", "FAIL"}


def test_duplicates_warning(tmp_path: Path) -> None:
    rules_path = _write_rules(tmp_path)
    df_dupes = pd.DataFrame(
        {
            "id": [1, 1, 2],
            "value": [10.0, 10.0, 20.0],
            "category": ["A", "A", "B"],
        }
    )

    checker = DataQualityChecker(df_dupes, rules_path=rules_path)
    report = checker.run_all_checks()

    assert any(issue.check == "duplicates" for issue in report.issues)


def test_inconsistent_data_types_fail(tmp_path: Path) -> None:
    rules_path = _write_rules(tmp_path)
    df_bad_types = pd.DataFrame(
        {
            "id": ["1", "2", "3"],
            "value": [10.0, 11.0, 12.0],
            "category": ["A", "B", "C"],
        }
    )

    checker = DataQualityChecker(df_bad_types, rules_path=rules_path)
    report = checker.run_all_checks()

    assert report.status == "FAIL"
    assert any(issue.check == "data_types" for issue in report.issues)


def test_integer_column_with_nulls_does_not_fail_data_types(tmp_path: Path) -> None:
    rules_path = _write_rules(tmp_path)
    df_integer_like_with_null = pd.DataFrame(
        {
            "id": [1.0, 2.0, None, 4.0],
            "value": [10.0, 11.0, 12.0, 13.0],
            "category": ["A", "B", "C", "D"],
        }
    )

    checker = DataQualityChecker(df_integer_like_with_null, rules_path=rules_path)
    report = checker.run_all_checks()

    assert not any(
        issue.check == "data_types" and issue.severity == "FAIL" for issue in report.issues
    )


def test_outliers_warning(tmp_path: Path) -> None:
    rules_path = _write_rules(tmp_path)
    df_outlier = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "value": [10.0, 11.0, 12.0, 13.0, 1000.0],
            "category": ["A", "B", "C", "D", "E"],
        }
    )

    checker = DataQualityChecker(df_outlier, rules_path=rules_path)
    report = checker.run_all_checks()

    assert any(issue.check == "outliers" for issue in report.issues)


def test_rules_file_not_found_raises() -> None:
    dataframe = pd.DataFrame({"id": [1], "value": [1.0], "category": ["A"]})

    with pytest.raises(FileNotFoundError):
        DataQualityChecker(dataframe, rules_path="config/does_not_exist.yaml")
