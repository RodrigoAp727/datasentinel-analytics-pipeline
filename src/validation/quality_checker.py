"""Data quality validation utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from loguru import logger


@dataclass(slots=True)
class QualityIssue:
    """Represents a data quality issue found during validation.

    Attributes:
        check: Validation check name.
        severity: Issue severity (WARNING or FAIL).
        message: Human-readable issue description.
        affected_columns: Columns related to the issue.
        details: Additional structured information.
    """

    check: str
    severity: str
    message: str
    affected_columns: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QualityReport:
    """Aggregated quality report for a DataFrame.

    Attributes:
        status: Overall status (PASS, WARNING, FAIL).
        issues: List of detected quality issues.
        score: Numeric quality score from 0 to 100.
    """

    status: str
    issues: list[QualityIssue]
    score: float


class DataQualityChecker:
    """Runs configurable data quality checks over a DataFrame.

    Args:
        dataframe: DataFrame to validate.
        rules_path: Path to YAML file containing quality rules.

    Raises:
        FileNotFoundError: If rules file cannot be found.
        ValueError: If rules file is invalid.
    """

    def __init__(
        self,
        dataframe: pd.DataFrame,
        rules_path: Path | str = "config/quality_rules.yaml",
    ) -> None:
        self.dataframe = dataframe.copy()
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules(self.rules_path)

    def run_all_checks(self) -> QualityReport:
        """Execute all configured checks and return a quality report.

        Returns:
            A QualityReport containing status, issues, and quality score.
        """
        logger.info("Starting quality checks using rules file={}", self.rules_path)
        issues: list[QualityIssue] = []

        issues.extend(self._check_required_columns())
        issues.extend(self._check_null_threshold())
        issues.extend(self._check_duplicates())
        issues.extend(self._check_data_types())
        issues.extend(self._check_outliers())

        status = self._compute_status(issues)
        score = self._compute_score(issues)

        logger.info(
            "Quality checks completed with status={}, score={}, issues={}",
            status,
            score,
            len(issues),
        )
        return QualityReport(status=status, issues=issues, score=score)

    @staticmethod
    def _load_rules(rules_path: Path) -> dict[str, Any]:
        """Load quality rules from YAML file."""
        if not rules_path.exists():
            raise FileNotFoundError(f"Rules file not found: {rules_path}")

        try:
            with rules_path.open("r", encoding="utf-8") as stream:
                data = yaml.safe_load(stream) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML file: {rules_path}") from exc

        if not isinstance(data, dict):
            raise ValueError("Quality rules YAML must contain a top-level mapping")

        return data

    def _check_required_columns(self) -> list[QualityIssue]:
        """Validate whether required columns are present."""
        logger.info("Running required columns check")
        required_columns = self.rules.get("required_columns", [])
        missing = [column for column in required_columns if column not in self.dataframe.columns]

        if not missing:
            return []

        return [
            QualityIssue(
                check="required_columns",
                severity="FAIL",
                message=f"Missing required columns: {missing}",
                affected_columns=missing,
                details={"missing_count": len(missing)},
            )
        ]

    def _check_null_threshold(self) -> list[QualityIssue]:
        """Validate null ratios against the configured threshold."""
        logger.info("Running null threshold check")
        threshold = float(self.rules.get("null_threshold", 0.2))
        issues: list[QualityIssue] = []

        null_ratios = self.dataframe.isna().mean()
        for column, ratio in null_ratios.items():
            if ratio > threshold:
                issues.append(
                    QualityIssue(
                        check="null_threshold",
                        severity="WARNING",
                        message=(
                            f"Column '{column}' has null ratio {ratio:.2%}, "
                            f"above threshold {threshold:.2%}"
                        ),
                        affected_columns=[column],
                        details={"ratio": float(ratio), "threshold": threshold},
                    )
                )

        return issues

    def _check_duplicates(self) -> list[QualityIssue]:
        """Validate duplicated rows against configured threshold."""
        logger.info("Running duplicates check")
        duplicate_threshold = float(self.rules.get("duplicate_ratio_threshold", 0.0))
        duplicate_count = int(self.dataframe.duplicated().sum())
        total_rows = len(self.dataframe)

        if total_rows == 0 or duplicate_count == 0:
            return []

        duplicate_ratio = duplicate_count / total_rows
        if duplicate_ratio <= duplicate_threshold:
            return []

        return [
            QualityIssue(
                check="duplicates",
                severity="WARNING",
                message=(
                    f"Duplicate ratio {duplicate_ratio:.2%} is above threshold "
                    f"{duplicate_threshold:.2%}"
                ),
                details={
                    "duplicate_count": duplicate_count,
                    "total_rows": total_rows,
                    "ratio": duplicate_ratio,
                    "threshold": duplicate_threshold,
                },
            )
        ]

    def _check_data_types(self) -> list[QualityIssue]:
        """Validate DataFrame column dtypes against expected schema types."""
        logger.info("Running data type consistency check")
        expected_types: dict[str, str] = self.rules.get("expected_types", {})
        issues: list[QualityIssue] = []

        for column, expected in expected_types.items():
            if column not in self.dataframe.columns:
                continue

            if self._is_dtype_compatible(self.dataframe[column], expected):
                continue

            issues.append(
                QualityIssue(
                    check="data_types",
                    severity="FAIL",
                    message=(
                        f"Column '{column}' has dtype '{self.dataframe[column].dtype}', "
                        f"expected '{expected}'"
                    ),
                    affected_columns=[column],
                    details={
                        "observed_dtype": str(self.dataframe[column].dtype),
                        "expected_dtype": expected,
                    },
                )
            )

        return issues

    def _check_outliers(self) -> list[QualityIssue]:
        """Validate outlier ratio per numeric column using IQR or z-score."""
        logger.info("Running outlier detection check")
        config = self.rules.get("outlier_detection", {})
        method = str(config.get("method", "iqr")).lower()
        ratio_threshold = float(config.get("max_outlier_ratio", 0.05))
        zscore_threshold = float(config.get("zscore_threshold", 3.0))

        configured_columns = config.get("columns")
        if configured_columns:
            columns = [col for col in configured_columns if col in self.dataframe.columns]
        else:
            columns = list(self.dataframe.select_dtypes(include=[np.number]).columns)

        issues: list[QualityIssue] = []
        for column in columns:
            series = self.dataframe[column].dropna()
            if series.empty:
                continue

            if method == "zscore":
                outlier_ratio = self._zscore_outlier_ratio(series, zscore_threshold)
            else:
                outlier_ratio = self._iqr_outlier_ratio(series)

            if outlier_ratio > ratio_threshold:
                issues.append(
                    QualityIssue(
                        check="outliers",
                        severity="WARNING",
                        message=(
                            f"Column '{column}' outlier ratio {outlier_ratio:.2%} "
                            f"is above threshold {ratio_threshold:.2%}"
                        ),
                        affected_columns=[column],
                        details={
                            "method": method,
                            "ratio": outlier_ratio,
                            "threshold": ratio_threshold,
                        },
                    )
                )

        return issues

    @staticmethod
    def _is_dtype_compatible(series: pd.Series, expected: str) -> bool:
        """Check whether an observed dtype is compatible with expected type."""
        expected_lower = expected.lower()
        non_null = series.dropna()

        if expected_lower in {"int", "integer"}:
            if pd.api.types.is_integer_dtype(series):
                return True
            if pd.api.types.is_float_dtype(series):
                if non_null.empty:
                    return True
                return bool(np.isclose(non_null % 1, 0).all())
            return False
        if expected_lower in {"float", "double"}:
            return pd.api.types.is_numeric_dtype(series)
        if expected_lower in {"numeric", "number"}:
            return pd.api.types.is_numeric_dtype(series)
        if expected_lower in {"str", "string", "object"}:
            return pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)
        if expected_lower in {"bool", "boolean"}:
            return pd.api.types.is_bool_dtype(series)
        if expected_lower in {"datetime", "datetime64"}:
            return pd.api.types.is_datetime64_any_dtype(series)

        return str(series.dtype).lower() == expected_lower

    @staticmethod
    def _iqr_outlier_ratio(series: pd.Series) -> float:
        """Compute outlier ratio using IQR boundaries."""
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return 0.0

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = ((series < lower) | (series > upper)).sum()
        return float(outliers / len(series))

    @staticmethod
    def _zscore_outlier_ratio(series: pd.Series, threshold: float) -> float:
        """Compute outlier ratio using absolute z-score threshold."""
        std = series.std(ddof=0)
        if std == 0:
            return 0.0

        z_scores = ((series - series.mean()) / std).abs()
        outliers = (z_scores > threshold).sum()
        return float(outliers / len(series))

    @staticmethod
    def _compute_status(issues: list[QualityIssue]) -> str:
        """Compute overall quality status based on issue severities."""
        severities = {issue.severity for issue in issues}
        if "FAIL" in severities:
            return "FAIL"
        if "WARNING" in severities:
            return "WARNING"
        return "PASS"

    @staticmethod
    def _compute_score(issues: list[QualityIssue]) -> float:
        """Compute quality score between 0 and 100."""
        penalty = 0
        for issue in issues:
            if issue.severity == "FAIL":
                penalty += 30
            elif issue.severity == "WARNING":
                penalty += 10

        return float(max(0, 100 - penalty))
