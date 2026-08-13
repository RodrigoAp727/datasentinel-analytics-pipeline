from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from analysis.anomaly_detector import AnomalyFinding, AnomalyReport
from notifications.notifier import Notifier, SMTPConfig
from validation.quality_checker import QualityIssue, QualityReport


def _quality_report(status: str) -> QualityReport:
    issues = []
    if status in {"WARNING", "FAIL"}:
        issues = [
            QualityIssue(
                check="null_threshold",
                severity="WARNING" if status == "WARNING" else "FAIL",
                message="Issue found",
                affected_columns=["value"],
                details={},
            )
        ]

    score = 95.0 if status == "PASS" else 70.0 if status == "WARNING" else 40.0
    return QualityReport(status=status, issues=issues, score=score)


def _anomaly_report(high: bool) -> AnomalyReport:
    if not high:
        return AnomalyReport(anomalies=[])

    return AnomalyReport(
        anomalies=[
            AnomalyFinding(
                column="value",
                index=10,
                severity="alta",
                method="zscore",
                value=999.0,
                score=4.3,
                message="Anomalia critica",
            )
        ]
    )


@patch("notifications.notifier.requests.post")
def test_send_slack_alert_urgent_when_quality_fail(mock_post: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    notifier = Notifier(
        quality_report=_quality_report("FAIL"),
        anomaly_report=_anomaly_report(high=False),
        slack_webhook_url="https://hooks.slack.com/services/T000/B000/XXX",
    )

    result = notifier.send_slack_alert()

    assert result is True
    sent_payload = mock_post.call_args.kwargs["json"]
    header_text = sent_payload["blocks"][0]["text"]["text"]
    assert "ALERTA URGENTE" in header_text


@patch("notifications.notifier.requests.post")
def test_send_slack_alert_info_when_warning_without_high_anomaly(
    mock_post: MagicMock,
) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    notifier = Notifier(
        quality_report=_quality_report("WARNING"),
        anomaly_report=_anomaly_report(high=False),
        slack_webhook_url="https://hooks.slack.com/services/T000/B000/XXX",
    )

    result = notifier.send_slack_alert()

    assert result is True
    sent_payload = mock_post.call_args.kwargs["json"]
    header_text = sent_payload["blocks"][0]["text"]["text"]
    assert "Resumo Informativo" in header_text


@patch("notifications.notifier.requests.post")
def test_send_slack_alert_logs_and_returns_false_on_failure(mock_post: MagicMock) -> None:
    mock_post.side_effect = requests.RequestException("network down")

    notifier = Notifier(
        quality_report=_quality_report("PASS"),
        anomaly_report=_anomaly_report(high=False),
        slack_webhook_url="https://hooks.slack.com/services/T000/B000/XXX",
    )

    result = notifier.send_slack_alert()

    assert result is False


@patch("notifications.notifier.smtplib.SMTP")
def test_send_email_alert_urgent_when_high_anomaly(mock_smtp_cls: MagicMock) -> None:
    smtp_instance = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = smtp_instance

    notifier = Notifier(
        quality_report=_quality_report("PASS"),
        anomaly_report=_anomaly_report(high=True),
        smtp_config=SMTPConfig(
            host="smtp.example.com",
            port=587,
            user="bot@example.com",
            password="secret",
            use_tls=True,
        ),
    )

    result = notifier.send_email_alert(to_email="ops@example.com")

    assert result is True
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with("bot@example.com", "secret")
    sendmail_args = smtp_instance.sendmail.call_args.args
    assert sendmail_args[0] == "bot@example.com"
    assert sendmail_args[1] == ["ops@example.com"]
    assert "[DataSentinel][URGENTE]" in sendmail_args[2]


@patch("notifications.notifier.smtplib.SMTP")
def test_send_email_alert_returns_false_on_smtp_failure(mock_smtp_cls: MagicMock) -> None:
    smtp_instance = MagicMock()
    smtp_instance.sendmail.side_effect = Exception("smtp failed")
    mock_smtp_cls.return_value.__enter__.return_value = smtp_instance

    notifier = Notifier(
        quality_report=_quality_report("WARNING"),
        anomaly_report=_anomaly_report(high=False),
        smtp_config=SMTPConfig(
            host="smtp.example.com",
            port=587,
            user="bot@example.com",
            password="secret",
            use_tls=True,
        ),
    )

    result = notifier.send_email_alert(to_email="ops@example.com")

    assert result is False
