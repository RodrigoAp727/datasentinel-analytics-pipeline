"""Statistical anomaly detection utilities for tabular time series data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from loguru import logger

Severity = Literal["baixa", "media", "alta"]
AnomalyMethod = Literal["zscore", "rolling_std", "trend_change"]


@dataclass(slots=True)
class AnomalyFinding:
    """Represents one detected anomaly point.

    Attributes:
        column: Column where the anomaly was detected.
        index: Original index label of the affected row.
        severity: Severity level based on anomaly magnitude.
        method: Statistical method used to detect the anomaly.
        value: Observed value at the anomaly point.
        score: Standardized anomaly score for the chosen method.
        message: Human-readable explanation.
    """

    column: str
    index: object
    severity: Severity
    method: AnomalyMethod
    value: float
    score: float
    message: str


@dataclass(slots=True)
class AnomalyReport:
    """Aggregated anomaly detection output.

    Attributes:
        anomalies: List of anomalies found.
    """

    anomalies: list[AnomalyFinding] = field(default_factory=list)


class AnomalyDetector:
    """Detects anomalies and abrupt changes in numeric time series columns.

    The detector is domain-agnostic because it only relies on statistical
    properties from observed values (distribution, dispersion, and relative
    variation), not on business-specific thresholds or labels.

    Args:
        dataframe: Source DataFrame containing one or more numeric series.
    """

    def __init__(self, dataframe: pd.DataFrame) -> None:
        self.dataframe = dataframe.copy()

    def detect_time_series_anomalies(
        self,
        column: str,
        *,
        method: Literal["zscore", "rolling_std"] = "zscore",
        zscore_threshold: float = 3.0,
        rolling_window: int = 5,
        rolling_std_multiplier: float = 3.0,
    ) -> AnomalyReport:
        """Detect point anomalies in a time series column.

        Statistical logic:
        - zscore: computes $z_i = (x_i - \\mu) / \\sigma$ and flags points with
          $|z_i| > threshold$.
        - rolling_std: computes rolling mean/std over a moving window and flags
          points where $|x_i - mean_i| > k * std_i$.

        Args:
            column: Numeric column name to analyze.
            method: Detection method ("zscore" or "rolling_std").
            zscore_threshold: Absolute z-score threshold.
            rolling_window: Window size for rolling statistics.
            rolling_std_multiplier: Multiplier k for rolling std rule.

        Returns:
            AnomalyReport with all detected anomalies for the selected column.

        Raises:
            ValueError: If column does not exist, is non-numeric, or parameters
                are invalid.
        """
        logger.info(
            "Starting anomaly detection for column={} with method={}",
            column,
            method,
        )
        series = self._validate_numeric_series(column)

        if method == "zscore":
            report = self._detect_with_zscore(series, zscore_threshold)
        elif method == "rolling_std":
            report = self._detect_with_rolling_std(
                series,
                rolling_window=rolling_window,
                rolling_std_multiplier=rolling_std_multiplier,
            )
        else:
            raise ValueError("method must be either 'zscore' or 'rolling_std'")

        logger.info(
            "Anomaly detection completed for column={} with anomalies={}",
            column,
            len(report.anomalies),
        )
        return report

    def detect_trend_changes(
        self,
        column: str,
        *,
        pct_change_threshold: float = 0.30,
    ) -> AnomalyReport:
        """Detect abrupt trend changes using period-over-period variation.

        Statistical logic:
        Let $r_i = (x_i - x_{i-1}) / x_{i-1}$ be the relative change. A trend
        change is flagged when $|r_i| > threshold$.

        Args:
            column: Numeric column name to analyze.
            pct_change_threshold: Absolute percent-change threshold in decimal
                scale (e.g. 0.30 means 30%).

        Returns:
            AnomalyReport with abrupt trend change points.

        Raises:
            ValueError: If column is invalid or threshold is non-positive.
        """
        if pct_change_threshold <= 0:
            raise ValueError("pct_change_threshold must be > 0")

        logger.info(
            "Starting trend change detection for column={} with threshold={}",
            column,
            pct_change_threshold,
        )
        series = self._validate_numeric_series(column)

        pct_changes = series.pct_change().replace([np.inf, -np.inf], np.nan)
        mask = pct_changes.abs() > pct_change_threshold

        anomalies: list[AnomalyFinding] = []
        for idx in series[mask].index:
            score = float(abs(pct_changes.loc[idx]) / pct_change_threshold)
            severity = self._severity_from_score(score)
            anomalies.append(
                AnomalyFinding(
                    column=column,
                    index=idx,
                    severity=severity,
                    method="trend_change",
                    value=float(series.loc[idx]),
                    score=score,
                    message=(
                        "Variação percentual abrupta detectada: "
                        f"{float(pct_changes.loc[idx]):.2%}"
                    ),
                )
            )

        logger.info(
            "Trend change detection completed for column={} with anomalies={}",
            column,
            len(anomalies),
        )
        return AnomalyReport(anomalies=anomalies)

    def summarize_statistics(self, columns: list[str] | None = None) -> pd.DataFrame:
        """Generate compact descriptive statistics for numeric columns.

        Statistical logic:
        Uses descriptive metrics from central tendency, dispersion and
        quantiles: count, mean, std, min, 25%, 50%, 75%, max.

        Args:
            columns: Optional list of numeric columns. If omitted, all numeric
                columns are summarized.

        Returns:
            DataFrame indexed by column with descriptive statistics.

        Raises:
            ValueError: If no numeric columns are available.
        """
        if columns is None:
            target_df = self.dataframe.select_dtypes(include=[np.number])
        else:
            missing = [col for col in columns if col not in self.dataframe.columns]
            if missing:
                raise ValueError(f"Columns not found: {missing}")
            target_df = self.dataframe[columns].select_dtypes(include=[np.number])

        if target_df.empty:
            raise ValueError("No numeric columns available for summary")

        logger.info("Generating descriptive statistics for columns={}", list(target_df.columns))
        summary = target_df.describe().transpose()
        return summary

    def detect_across_columns(
        self,
        columns: list[str] | None = None,
        *,
        time_series_method: Literal["zscore", "rolling_std"] = "zscore",
        zscore_threshold: float = 3.0,
        rolling_window: int = 5,
        rolling_std_multiplier: float = 3.0,
        pct_change_threshold: float = 0.30,
    ) -> AnomalyReport:
        """Run anomaly and trend checks across multiple numeric columns.

        Args:
            columns: Optional subset of numeric columns.
            time_series_method: Method for point anomaly detection.
            zscore_threshold: Z-score threshold when using zscore.
            rolling_window: Window size when using rolling_std.
            rolling_std_multiplier: Std multiplier when using rolling_std.
            pct_change_threshold: Threshold for trend change detection.

        Returns:
            Combined AnomalyReport with findings from all selected columns.
        """
        if columns is None:
            columns = list(self.dataframe.select_dtypes(include=[np.number]).columns)

        all_anomalies: list[AnomalyFinding] = []
        logger.info("Running cross-column anomaly scan for columns={}", columns)

        for column in columns:
            ts_report = self.detect_time_series_anomalies(
                column,
                method=time_series_method,
                zscore_threshold=zscore_threshold,
                rolling_window=rolling_window,
                rolling_std_multiplier=rolling_std_multiplier,
            )
            trend_report = self.detect_trend_changes(
                column,
                pct_change_threshold=pct_change_threshold,
            )
            all_anomalies.extend(ts_report.anomalies)
            all_anomalies.extend(trend_report.anomalies)

        return AnomalyReport(anomalies=all_anomalies)

    def _validate_numeric_series(self, column: str) -> pd.Series:
        """Validate and return a numeric series without missing values."""
        if column not in self.dataframe.columns:
            raise ValueError(f"Column not found: {column}")

        series = self.dataframe[column]
        if not pd.api.types.is_numeric_dtype(series):
            raise ValueError(f"Column is not numeric: {column}")

        cleaned = series.dropna()
        if cleaned.empty:
            raise ValueError(f"Column has no valid numeric values: {column}")

        return cleaned

    def _detect_with_zscore(self, series: pd.Series, threshold: float) -> AnomalyReport:
        """Detect anomalies with global z-score thresholding."""
        if threshold <= 0:
            raise ValueError("zscore_threshold must be > 0")

        mean = series.mean()
        std = series.std(ddof=0)
        if std == 0:
            return AnomalyReport(anomalies=[])

        z_scores = (series - mean) / std
        mask = z_scores.abs() > threshold

        anomalies: list[AnomalyFinding] = []
        column = str(series.name)
        for idx in series[mask].index:
            abs_score = float(abs(z_scores.loc[idx]))
            anomalies.append(
                AnomalyFinding(
                    column=column,
                    index=idx,
                    severity=self._severity_from_score(abs_score / threshold),
                    method="zscore",
                    value=float(series.loc[idx]),
                    score=abs_score,
                    message=(
                        f"Ponto fora do limiar de z-score: |z|={abs_score:.2f} "
                        f"(threshold={threshold:.2f})"
                    ),
                )
            )

        return AnomalyReport(anomalies=anomalies)

    def _detect_with_rolling_std(
        self,
        series: pd.Series,
        *,
        rolling_window: int,
        rolling_std_multiplier: float,
    ) -> AnomalyReport:
        """Detect anomalies using rolling mean and rolling std boundaries."""
        if rolling_window < 2:
            raise ValueError("rolling_window must be >= 2")
        if rolling_std_multiplier <= 0:
            raise ValueError("rolling_std_multiplier must be > 0")

        # Use only historical points to evaluate the current value and avoid
        # leaking the potential anomaly into its own baseline.
        rolling_mean = (
            series.rolling(window=rolling_window, min_periods=rolling_window).mean().shift(1)
        )
        rolling_std = (
            series.rolling(window=rolling_window, min_periods=rolling_window).std(ddof=0).shift(1)
        )

        valid_mask = rolling_std > 0
        deviation = (series - rolling_mean).abs()
        limit = rolling_std_multiplier * rolling_std
        anomaly_mask = valid_mask & (deviation > limit)

        anomalies: list[AnomalyFinding] = []
        column = str(series.name)
        for idx in series[anomaly_mask].index:
            score = float(deviation.loc[idx] / limit.loc[idx])
            anomalies.append(
                AnomalyFinding(
                    column=column,
                    index=idx,
                    severity=self._severity_from_score(score),
                    method="rolling_std",
                    value=float(series.loc[idx]),
                    score=score,
                    message=(
                        "Desvio acima do limite movel: "
                        f"|x-mean|={float(deviation.loc[idx]):.4f}, "
                        f"limite={float(limit.loc[idx]):.4f}"
                    ),
                )
            )

        return AnomalyReport(anomalies=anomalies)

    @staticmethod
    def _severity_from_score(score: float) -> Severity:
        """Map normalized score to severity level."""
        if score >= 2.0:
            return "alta"
        if score >= 1.5:
            return "media"
        return "baixa"
