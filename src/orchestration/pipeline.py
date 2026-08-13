"""Pipeline orchestration for DataSentinel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from loguru import logger

from analysis.anomaly_detector import AnomalyDetector, AnomalyReport
from config.settings import Settings, get_settings
from ingestion.data_loader import APISource, CSVSource, DataLoader
from notifications.notifier import Notifier, SMTPConfig
from reporting.report_generator import ReportGenerator
from validation.quality_checker import DataQualityChecker, QualityReport

CheckerFactory = Callable[[pd.DataFrame, Path | str], DataQualityChecker]
DetectorFactory = Callable[[pd.DataFrame], AnomalyDetector]
ReportFactory = Callable[
    [pd.DataFrame, QualityReport, AnomalyReport, Path | str],
    ReportGenerator,
]
NotifierFactory = Callable[
    [QualityReport, AnomalyReport, str | None, SMTPConfig | None],
    Notifier,
]


@dataclass(slots=True)
class SourceRunResult:
    """Execution result for a single loaded source."""

    source_name: str
    quality_status: str = "NOT_RUN"
    anomaly_count: int = 0
    reports_generated: bool = False
    notified: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PipelineRunResult:
    """Execution result for the full pipeline."""

    success: bool
    stage_status: dict[str, str]
    source_results: list[SourceRunResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DataPipeline:
    """Orchestrates ingestion, validation, analysis, reporting and notifications.

    The run method is resilient: if a stage fails it logs the error, attempts a
    Slack notification, and keeps execution alive without raising.

    Args:
        csv_sources: Optional CSV sources for ingestion.
        api_sources: Optional API sources for ingestion.
        rules_path: Path to quality rules YAML.
        reports_dir: Output directory for generated reports.
        slack_webhook_url: Optional Slack webhook URL.
        smtp_config: Optional SMTP config for email notifications.
        email_to: Optional recipient for email notifications.
        loader: Optional DataLoader instance for dependency injection.
        checker_factory: Optional factory for DataQualityChecker.
        detector_factory: Optional factory for AnomalyDetector.
        report_factory: Optional factory for ReportGenerator.
        notifier_factory: Optional factory for Notifier.
        settings: Optional typed settings object.
    """

    def __init__(
        self,
        *,
        csv_sources: list[CSVSource] | None = None,
        api_sources: list[APISource] | None = None,
        rules_path: Path | str = "config/quality_rules.yaml",
        reports_dir: Path | str = "reports",
        slack_webhook_url: str | None = None,
        smtp_config: SMTPConfig | None = None,
        email_to: str | None = None,
        loader: DataLoader | None = None,
        checker_factory: CheckerFactory | None = None,
        detector_factory: DetectorFactory | None = None,
        report_factory: ReportFactory | None = None,
        notifier_factory: NotifierFactory | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved_settings = settings or self._safe_load_settings()

        self.csv_sources = csv_sources or self._default_csv_sources(resolved_settings)
        self.api_sources = api_sources or []
        self.rules_path = rules_path
        self.reports_dir = reports_dir
        self.slack_webhook_url = slack_webhook_url or (
            resolved_settings.slack_webhook_url if resolved_settings else None
        )
        self.smtp_config = smtp_config or self._default_smtp_config(resolved_settings)
        self.email_to = email_to or (resolved_settings.smtp_user if resolved_settings else None)

        self.loader = loader or DataLoader()
        self.checker_factory = checker_factory or (
            lambda df, rules_path: DataQualityChecker(df, rules_path=rules_path)
        )
        self.detector_factory = detector_factory or (lambda df: AnomalyDetector(df))
        self.report_factory = report_factory or (
            lambda df, quality_report, anomaly_report, reports_dir: ReportGenerator(
                dataframe=df,
                quality_report=quality_report,
                anomaly_report=anomaly_report,
                reports_dir=reports_dir,
            )
        )
        self.notifier_factory = notifier_factory or (
            lambda quality_report, anomaly_report, slack_webhook_url, smtp_config: Notifier(
                quality_report=quality_report,
                anomaly_report=anomaly_report,
                slack_webhook_url=slack_webhook_url,
                smtp_config=smtp_config,
            )
        )

    def run(self) -> PipelineRunResult:
        """Run the complete pipeline without raising stage failures.

        Returns:
            PipelineRunResult with statuses and collected errors.
        """
        stage_status: dict[str, str] = {
            "ingestion": "NOT_RUN",
            "validation": "NOT_RUN",
            "analysis": "NOT_RUN",
            "reporting": "NOT_RUN",
            "notification": "NOT_RUN",
        }
        errors: list[str] = []
        source_results: list[SourceRunResult] = []

        logger.info("Pipeline started")

        try:
            datasets = self.loader.load_sources(
                csv_sources=self.csv_sources,
                api_sources=self.api_sources,
            )
            stage_status["ingestion"] = "SUCCESS"
            logger.info("Ingestion completed with sources={}", list(datasets.keys()))
        except Exception as exc:
            stage_status["ingestion"] = "FAILED"
            message = f"Ingestion failed: {exc}"
            errors.append(message)
            logger.exception(message)
            self._notify_pipeline_error(stage="ingestion", error_message=message)
            return PipelineRunResult(
                success=False,
                stage_status=stage_status,
                source_results=source_results,
                errors=errors,
            )

        if not datasets:
            stage_status["ingestion"] = "FAILED"
            message = "Ingestion produced no datasets"
            errors.append(message)
            logger.error(message)
            self._notify_pipeline_error(stage="ingestion", error_message=message)
            return PipelineRunResult(
                success=False,
                stage_status=stage_status,
                source_results=source_results,
                errors=errors,
            )

        for source_name, dataframe in datasets.items():
            source_result = SourceRunResult(source_name=source_name)
            quality_report: QualityReport | None = None
            anomaly_report: AnomalyReport | None = None

            try:
                checker = self.checker_factory(dataframe, self.rules_path)
                quality_report = checker.run_all_checks()
                source_result.quality_status = quality_report.status
                stage_status["validation"] = "SUCCESS"
            except Exception as exc:
                source_result.quality_status = "FAILED"
                error = f"Validation failed for source={source_name}: {exc}"
                source_result.errors.append(error)
                errors.append(error)
                stage_status["validation"] = "FAILED"
                logger.exception(error)
                self._notify_pipeline_error(stage="validation", error_message=error)

            try:
                detector = self.detector_factory(dataframe)
                anomaly_report = detector.detect_across_columns()
                source_result.anomaly_count = len(anomaly_report.anomalies)
                stage_status["analysis"] = "SUCCESS"
            except Exception as exc:
                error = f"Analysis failed for source={source_name}: {exc}"
                source_result.errors.append(error)
                errors.append(error)
                stage_status["analysis"] = "FAILED"
                logger.exception(error)
                self._notify_pipeline_error(stage="analysis", error_message=error)

            if quality_report is not None and anomaly_report is not None:
                try:
                    report_generator = self.report_factory(
                        dataframe,
                        quality_report,
                        anomaly_report,
                        self.reports_dir,
                    )
                    report_generator.generate_reports()
                    source_result.reports_generated = True
                    stage_status["reporting"] = "SUCCESS"
                except Exception as exc:
                    error = f"Reporting failed for source={source_name}: {exc}"
                    source_result.errors.append(error)
                    errors.append(error)
                    stage_status["reporting"] = "FAILED"
                    logger.exception(error)
                    self._notify_pipeline_error(stage="reporting", error_message=error)

                try:
                    notifier = self.notifier_factory(
                        quality_report,
                        anomaly_report,
                        self.slack_webhook_url,
                        self.smtp_config,
                    )
                    slack_ok = notifier.send_slack_alert()
                    email_ok = True
                    if self.email_to:
                        email_ok = notifier.send_email_alert(to_email=self.email_to)
                    source_result.notified = bool(slack_ok or email_ok)
                    stage_status["notification"] = "SUCCESS"
                except Exception as exc:
                    error = f"Notification failed for source={source_name}: {exc}"
                    source_result.errors.append(error)
                    errors.append(error)
                    stage_status["notification"] = "FAILED"
                    logger.exception(error)

            source_results.append(source_result)

        success = not errors
        if success:
            logger.info("Pipeline completed successfully")
        else:
            logger.warning("Pipeline completed with errors count={}", len(errors))

        return PipelineRunResult(
            success=success,
            stage_status=stage_status,
            source_results=source_results,
            errors=errors,
        )

    def _notify_pipeline_error(self, *, stage: str, error_message: str) -> None:
        """Best-effort Slack notification when a pipeline stage fails."""
        try:
            fallback_quality = QualityReport(status="FAIL", issues=[], score=0.0)
            fallback_anomaly = AnomalyReport(anomalies=[])
            notifier = self.notifier_factory(
                fallback_quality,
                fallback_anomaly,
                self.slack_webhook_url,
                self.smtp_config,
            )
            notifier.send_slack_alert()
            logger.info("Error notification sent for stage={}", stage)
        except Exception as exc:
            logger.exception(
                "Failed to send error notification for stage={} with error={}",
                stage,
                exc,
            )

    @staticmethod
    def _safe_load_settings() -> Settings | None:
        """Load settings without breaking pipeline initialization."""
        try:
            return get_settings()
        except Exception as exc:
            logger.warning("Could not load settings from environment: {}", exc)
            return None

    @staticmethod
    def _default_csv_sources(settings: Settings | None) -> list[CSVSource]:
        """Build default CSV source from settings when available."""
        if settings and settings.data_source_path:
            return [CSVSource(name="local_csv", path=settings.data_source_path)]
        return []

    @staticmethod
    def _default_smtp_config(settings: Settings | None) -> SMTPConfig | None:
        """Build default SMTP configuration from settings when available."""
        if not settings:
            return None
        return SMTPConfig(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
        )
