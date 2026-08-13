from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pandas as pd

from analysis.anomaly_detector import AnomalyFinding, AnomalyReport
from ingestion.data_loader import CSVSource
from orchestration.pipeline import DataPipeline
from validation.quality_checker import QualityReport


@dataclass(slots=True)
class _DummySettings:
    slack_webhook_url: str = "https://hooks.slack.com/services/T000/B000/XXX"
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 587
    smtp_user: str = "bot@example.com"
    smtp_password: str = "secret"
    data_source_path: str = "dummy.csv"


def _quality_report_ok() -> QualityReport:
    return QualityReport(status="PASS", issues=[], score=98.0)


def _anomaly_report_ok() -> AnomalyReport:
    return AnomalyReport(
        anomalies=[
            AnomalyFinding(
                column="value",
                index=2,
                severity="baixa",
                method="zscore",
                value=42.0,
                score=2.2,
                message="anomaly",
            )
        ]
    )


def test_pipeline_run_full_flow_success_with_mocks() -> None:
    dataframe = pd.DataFrame({"id": [1, 2, 3], "value": [10.0, 20.0, 30.0]})

    loader = MagicMock()
    loader.load_sources.return_value = {"local_csv": dataframe}

    checker_instance = MagicMock()
    checker_instance.run_all_checks.return_value = _quality_report_ok()

    detector_instance = MagicMock()
    detector_instance.detect_across_columns.return_value = _anomaly_report_ok()

    report_instance = MagicMock()
    report_instance.generate_reports.return_value = {
        "excel": "reports/report_20260811_120000.xlsx",
        "html": "reports/report_20260811_120000.html",
    }

    notifier_instance = MagicMock()
    notifier_instance.send_slack_alert.return_value = True
    notifier_instance.send_email_alert.return_value = True

    pipeline = DataPipeline(
        csv_sources=[CSVSource(name="local_csv", path="dummy.csv")],
        loader=loader,
        checker_factory=lambda _df, _rules: checker_instance,
        detector_factory=lambda _df: detector_instance,
        report_factory=lambda _df, _q, _a, _r: report_instance,
        notifier_factory=lambda _q, _a, _webhook, _smtp: notifier_instance,
        settings=_DummySettings(),
        email_to="ops@example.com",
    )

    result = pipeline.run()

    assert result.success is True
    assert result.stage_status["ingestion"] == "SUCCESS"
    assert result.stage_status["validation"] == "SUCCESS"
    assert result.stage_status["analysis"] == "SUCCESS"
    assert result.stage_status["reporting"] == "SUCCESS"
    assert result.stage_status["notification"] == "SUCCESS"
    assert len(result.source_results) == 1
    assert result.source_results[0].reports_generated is True
    assert result.source_results[0].notified is True


def test_pipeline_run_ingestion_failure_notifies_without_raising() -> None:
    loader = MagicMock()
    loader.load_sources.side_effect = RuntimeError("boom ingestion")

    notifier_instance = MagicMock()
    notifier_instance.send_slack_alert.return_value = True

    pipeline = DataPipeline(
        csv_sources=[CSVSource(name="local_csv", path="dummy.csv")],
        loader=loader,
        notifier_factory=lambda _q, _a, _webhook, _smtp: notifier_instance,
        settings=_DummySettings(),
    )

    result = pipeline.run()

    assert result.success is False
    assert result.stage_status["ingestion"] == "FAILED"
    assert any("Ingestion failed" in error for error in result.errors)
    notifier_instance.send_slack_alert.assert_called_once()


def test_pipeline_run_validation_failure_continues_and_does_not_crash() -> None:
    dataframe = pd.DataFrame({"id": [1, 2, 3], "value": [10.0, 20.0, 30.0]})

    loader = MagicMock()
    loader.load_sources.return_value = {"local_csv": dataframe}

    detector_instance = MagicMock()
    detector_instance.detect_across_columns.return_value = _anomaly_report_ok()

    notifier_instance = MagicMock()
    notifier_instance.send_slack_alert.return_value = True

    pipeline = DataPipeline(
        csv_sources=[CSVSource(name="local_csv", path="dummy.csv")],
        loader=loader,
        checker_factory=lambda _df, _rules: (_ for _ in ()).throw(RuntimeError("bad validation")),
        detector_factory=lambda _df: detector_instance,
        notifier_factory=lambda _q, _a, _webhook, _smtp: notifier_instance,
        settings=_DummySettings(),
    )

    result = pipeline.run()

    assert result.success is False
    assert result.stage_status["ingestion"] == "SUCCESS"
    assert result.stage_status["validation"] == "FAILED"
    assert result.stage_status["analysis"] == "SUCCESS"
    assert any("Validation failed" in error for error in result.errors)
