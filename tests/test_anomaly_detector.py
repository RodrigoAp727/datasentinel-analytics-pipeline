from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.anomaly_detector import AnomalyDetector


def test_detect_time_series_anomalies_with_zscore() -> None:
    df = pd.DataFrame(
        {
            "sales": [100.0, 102.0, 99.0, 101.0, 98.0, 300.0, 100.0, 101.0],
        }
    )

    detector = AnomalyDetector(df)
    report = detector.detect_time_series_anomalies(
        "sales",
        method="zscore",
        zscore_threshold=2.0,
    )

    assert len(report.anomalies) >= 1
    anomaly_indexes = [finding.index for finding in report.anomalies]
    assert 5 in anomaly_indexes
    assert all(finding.column == "sales" for finding in report.anomalies)


def test_detect_time_series_anomalies_with_rolling_std() -> None:
    df = pd.DataFrame(
        {
            "operational_metric": [50.0, 49.5, 50.5, 50.0, 49.8, 80.0, 50.1, 49.9],
        }
    )

    detector = AnomalyDetector(df)
    report = detector.detect_time_series_anomalies(
        "operational_metric",
        method="rolling_std",
        rolling_window=4,
        rolling_std_multiplier=2.5,
    )

    assert len(report.anomalies) >= 1
    assert any(finding.index == 5 for finding in report.anomalies)


def test_detect_trend_changes_finds_abrupt_variation() -> None:
    df = pd.DataFrame(
        {
            "throughput": [100.0, 105.0, 110.0, 108.0, 170.0, 172.0],
        }
    )

    detector = AnomalyDetector(df)
    report = detector.detect_trend_changes("throughput", pct_change_threshold=0.25)

    assert len(report.anomalies) >= 1
    abrupt_indexes = [finding.index for finding in report.anomalies]
    assert 4 in abrupt_indexes
    assert all(finding.method == "trend_change" for finding in report.anomalies)


def test_summarize_statistics_returns_describe_output() -> None:
    df = pd.DataFrame(
        {
            "sales": [10.0, 20.0, 30.0, 40.0],
            "ops": [1.0, 2.0, 3.0, 4.0],
            "category": ["A", "B", "C", "D"],
        }
    )

    detector = AnomalyDetector(df)
    summary = detector.summarize_statistics()

    assert "sales" in summary.index
    assert "ops" in summary.index
    assert "mean" in summary.columns
    assert np.isclose(float(summary.loc["sales", "mean"]), 25.0)


def test_detect_across_columns_is_domain_agnostic() -> None:
    df = pd.DataFrame(
        {
            "sales": [100.0, 101.0, 99.0, 102.0, 350.0],
            "machine_load": [60.0, 61.0, 59.0, 60.5, 20.0],
        }
    )

    detector = AnomalyDetector(df)
    report = detector.detect_across_columns(
        columns=["sales", "machine_load"],
        time_series_method="zscore",
        zscore_threshold=1.7,
        pct_change_threshold=0.25,
    )

    assert len(report.anomalies) >= 2
    detected_columns = {finding.column for finding in report.anomalies}
    assert "sales" in detected_columns
    assert "machine_load" in detected_columns


def test_anomaly_report_contains_severity_column_and_index() -> None:
    df = pd.DataFrame(
        {
            "value": [10.0, 11.0, 9.0, 10.0, 80.0],
        }
    )

    detector = AnomalyDetector(df)
    report = detector.detect_time_series_anomalies(
        "value",
        method="zscore",
        zscore_threshold=1.8,
    )

    assert len(report.anomalies) >= 1
    finding = report.anomalies[0]
    assert finding.severity in {"baixa", "media", "alta"}
    assert finding.column == "value"
    assert isinstance(finding.index, int)
