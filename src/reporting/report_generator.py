"""Report generation utilities for quality and anomaly analysis."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from plotly import graph_objects as go
from plotly.subplots import make_subplots

from analysis.anomaly_detector import AnomalyReport
from reporting.data_profile import (
    build_column_profile_dataframe,
    build_written_summary_html,
)
from validation.quality_checker import QualityReport


class ReportGenerator:
    """Generate Excel and HTML reports for data quality and anomalies.

    Args:
        dataframe: Original DataFrame used in the pipeline.
        quality_report: Quality validation output.
        anomaly_report: Anomaly detection output.
        reports_dir: Output directory for report artifacts.
    """

    def __init__(
        self,
        dataframe: pd.DataFrame,
        quality_report: QualityReport,
        anomaly_report: AnomalyReport,
        reports_dir: Path | str = "reports",
    ) -> None:
        self.dataframe = dataframe.copy()
        self.quality_report = quality_report
        self.anomaly_report = anomaly_report
        self.reports_dir = Path(reports_dir)

    def generate_reports(self) -> dict[str, Path]:
        """Generate Excel and HTML reports using the same timestamp.

        Returns:
            Dictionary containing generated paths with keys "excel" and "html".
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = self.generate_excel_report(timestamp=timestamp)
        html_path = self.generate_html_report(timestamp=timestamp)
        return {"excel": excel_path, "html": html_path}

    def generate_excel_report(self, *, timestamp: str | None = None) -> Path:
        """Generate a multi-sheet Excel report.

        Sheets:
        - Resumo Executivo
        - Qualidade de Dados
        - Anomalias Detectadas
        - Dados Brutos

        Args:
            timestamp: Optional timestamp string. If omitted, current timestamp
                in format YYYYMMDD_HHMMSS is used.

        Returns:
            Path to the generated Excel report.
        """
        self._ensure_reports_dir()
        report_timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.reports_dir / f"report_{report_timestamp}.xlsx"

        logger.info("Generating Excel report at path={}", output_path)

        executive_df = self._build_executive_summary_dataframe(report_timestamp)
        profile_df = self._build_data_profile_dataframe()
        quality_issues_df = self._build_quality_issues_dataframe()
        anomalies_df = self._build_anomalies_dataframe()
        raw_data_df = self.dataframe.copy().reset_index(drop=False)

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            executive_df.to_excel(writer, sheet_name="Resumo Executivo", index=False)
            profile_df.to_excel(writer, sheet_name="Perfil da Base", index=False)
            quality_issues_df.to_excel(writer, sheet_name="Qualidade de Dados", index=False)
            anomalies_df.to_excel(writer, sheet_name="Anomalias Detectadas", index=False)
            raw_data_df.to_excel(writer, sheet_name="Dados Brutos", index=False)

        logger.info("Excel report generated successfully at path={}", output_path)
        return output_path

    def generate_html_report(self, *, timestamp: str | None = None) -> Path:
        """Generate an HTML report with interactive Plotly charts.

        Included charts:
        - Trends for numeric columns.
        - Anomaly severity distribution.
        - Quality score evolution over rows (as a temporal proxy).

        Args:
            timestamp: Optional timestamp string. If omitted, current timestamp
                in format YYYYMMDD_HHMMSS is used.

        Returns:
            Path to the generated HTML report.
        """
        self._ensure_reports_dir()
        report_timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.reports_dir / f"report_{report_timestamp}.html"

        logger.info("Generating HTML report at path={}", output_path)

        figure = make_subplots(
            rows=3,
            cols=1,
            subplot_titles=(
                "Tendencias das Series Numericas",
                "Distribuicao de Anomalias por Severidade",
                "Score de Qualidade ao Longo do Tempo",
            ),
            vertical_spacing=0.12,
        )

        self._add_trend_traces(figure)
        self._add_anomaly_distribution_trace(figure)
        self._add_quality_score_over_time_trace(figure)

        figure.update_layout(
            title="DataSentinel - Relatorio de Qualidade e Anomalias",
            height=1200,
            template="plotly_white",
            legend_title="Series",
        )

        executive_df = self._build_executive_summary_dataframe(report_timestamp)
        profile_df = self._build_data_profile_dataframe()
        quality_issues_df = self._build_quality_issues_dataframe()
        anomalies_df = self._build_anomalies_dataframe()
        html_table = executive_df.to_html(index=False, border=0, classes="summary-table")
        profile_table = profile_df.to_html(index=False, border=0, classes="summary-table")
        quality_table = quality_issues_df.to_html(
            index=False,
            border=0,
            classes="summary-table",
        )
        anomalies_table = anomalies_df.to_html(
            index=False,
            border=0,
            classes="summary-table",
        )
        written_summary_html = build_written_summary_html(
            self.dataframe,
            self.quality_report,
            self.anomaly_report,
        )
        kpi_cards_html = self._build_kpi_cards_html(report_timestamp)

        chart_html = figure.to_html(full_html=False, include_plotlyjs="cdn")
        full_html = self._compose_html_document(
            chart_html=chart_html,
            kpi_cards_html=kpi_cards_html,
            summary_table=html_table,
            written_summary_html=written_summary_html,
            profile_table=profile_table,
            quality_table=quality_table,
            anomalies_table=anomalies_table,
        )
        output_path.write_text(full_html, encoding="utf-8")

        logger.info("HTML report generated successfully at path={}", output_path)
        return output_path

    def _ensure_reports_dir(self) -> None:
        """Ensure output directory exists."""
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def _build_executive_summary_dataframe(self, timestamp: str) -> pd.DataFrame:
        """Build executive summary table used in Excel and HTML reports."""
        return pd.DataFrame(
            [
                {"metrica": "Gerado em", "valor": timestamp},
                {"metrica": "Total de linhas", "valor": int(len(self.dataframe))},
                {"metrica": "Total de colunas", "valor": int(self.dataframe.shape[1])},
                {"metrica": "Status de Qualidade", "valor": self.quality_report.status},
                {
                    "metrica": "Score de Qualidade",
                    "valor": float(round(self.quality_report.score, 2)),
                },
                {
                    "metrica": "Quantidade de Problemas de Qualidade",
                    "valor": int(len(self.quality_report.issues)),
                },
                {
                    "metrica": "Quantidade de Anomalias",
                    "valor": int(len(self.anomaly_report.anomalies)),
                },
            ]
        )

    def _build_quality_issues_dataframe(self) -> pd.DataFrame:
        """Convert quality issues to tabular format for report output."""
        if not self.quality_report.issues:
            return pd.DataFrame(
                [{"check": "", "severity": "", "message": "Nenhum problema encontrado"}]
            )

        rows: list[dict[str, Any]] = []
        for issue in self.quality_report.issues:
            rows.append(
                {
                    "check": issue.check,
                    "severity": issue.severity,
                    "message": issue.message,
                    "affected_columns": ", ".join(issue.affected_columns),
                    "details": str(issue.details),
                }
            )
        return pd.DataFrame(rows)

    def _build_data_profile_dataframe(self) -> pd.DataFrame:
        """Build a detailed profile of the received spreadsheet."""
        return build_column_profile_dataframe(self.dataframe)

    def _build_anomalies_dataframe(self) -> pd.DataFrame:
        """Convert anomaly findings to tabular format for report output."""
        if not self.anomaly_report.anomalies:
            return pd.DataFrame(
                [{"column": "", "index": "", "message": "Nenhuma anomalia detectada"}]
            )

        rows: list[dict[str, Any]] = []
        for anomaly in self.anomaly_report.anomalies:
            row = asdict(anomaly)
            rows.append(row)
        return pd.DataFrame(rows)

    def _build_kpi_cards_html(self, timestamp: str) -> str:
        """Build executive KPI cards for the HTML report header."""
        cards = [
            ("Status", self.quality_report.status),
            ("Score de Qualidade", f"{self.quality_report.score:.2f}"),
            ("Problemas", str(len(self.quality_report.issues))),
            ("Anomalias", str(len(self.anomaly_report.anomalies))),
            ("Linhas", str(len(self.dataframe))),
            ("Gerado em", timestamp),
        ]

        return "".join(
            (
                '<div class="kpi-card">'
                f'<span class="kpi-label">{label}</span>'
                f'<strong class="kpi-value">{value}</strong>'
                '</div>'
            )
            for label, value in cards
        )

    def _add_trend_traces(self, figure: go.Figure) -> None:
        """Add line traces for numeric columns to trend chart."""
        numeric_df = self.dataframe.select_dtypes(include="number")
        if numeric_df.empty:
            figure.add_trace(
                go.Scatter(x=[0], y=[0], mode="lines", name="sem_dados_numericos"),
                row=1,
                col=1,
            )
            return

        for column in numeric_df.columns[:5]:
            figure.add_trace(
                go.Scatter(
                    x=list(numeric_df.index),
                    y=numeric_df[column],
                    mode="lines",
                    name=f"trend_{column}",
                ),
                row=1,
                col=1,
            )

    def _add_anomaly_distribution_trace(self, figure: go.Figure) -> None:
        """Add bar chart showing anomaly severity distribution."""
        severities = [finding.severity for finding in self.anomaly_report.anomalies]
        if not severities:
            severity_labels = ["baixa", "media", "alta"]
            severity_values = [0, 0, 0]
        else:
            severity_series = pd.Series(severities)
            severity_counts = (
                severity_series.value_counts().reindex(["baixa", "media", "alta"], fill_value=0)
            )
            severity_labels = list(severity_counts.index)
            severity_values = severity_counts.tolist()

        figure.add_trace(
            go.Bar(
                x=severity_labels,
                y=severity_values,
                name="anomalias_por_severidade",
                marker_color=["#7cb342", "#f9a825", "#e53935"],
            ),
            row=2,
            col=1,
        )

    def _add_quality_score_over_time_trace(self, figure: go.Figure) -> None:
        """Add quality score evolution computed over cumulative rows.

        The score is a cumulative completeness proxy:
        score_i = (1 - cumulative_null_ratio_i) * 100
        """
        if self.dataframe.empty:
            figure.add_trace(
                go.Scatter(x=[0], y=[0], mode="lines+markers", name="score_qualidade"),
                row=3,
                col=1,
            )
            return

        cumulative_scores = self._compute_cumulative_quality_scores()
        figure.add_trace(
            go.Scatter(
                x=list(cumulative_scores.index),
                y=list(cumulative_scores.values),
                mode="lines+markers",
                name="score_qualidade",
                line={"color": "#1e88e5"},
            ),
            row=3,
            col=1,
        )

    def _compute_cumulative_quality_scores(self) -> pd.Series:
        """Compute cumulative quality score series from null completeness."""
        total_columns = self.dataframe.shape[1]
        if total_columns == 0:
            return pd.Series([100.0])

        nulls_per_row = self.dataframe.isna().sum(axis=1)
        cumulative_nulls = nulls_per_row.cumsum()
        cumulative_cells = pd.Series(
            [(i + 1) * total_columns for i in range(len(self.dataframe))],
            index=self.dataframe.index,
            dtype="float64",
        )

        null_ratio = cumulative_nulls / cumulative_cells
        score_series = (1 - null_ratio) * 100
        return score_series.round(2)

    @staticmethod
    def _compose_html_document(
        *,
        chart_html: str,
                kpi_cards_html: str,
        summary_table: str,
        written_summary_html: str,
        profile_table: str,
                quality_table: str,
                anomalies_table: str,
    ) -> str:
        """Compose final HTML document with summary and charts."""
        return f"""<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>DataSentinel Report</title>
  <style>
        :root {{
            --bg-main: #07111f;
            --bg-panel: #0f1b2d;
            --border-soft: rgba(148, 163, 184, 0.18);
            --text-main: #e5eef9;
            --text-soft: #9fb0c7;
            --accent-soft: rgba(56, 189, 248, 0.16);
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, sans-serif;
            margin: 0;
            color: var(--text-main);
            background:
                radial-gradient(1200px 520px at 10% -10%, rgba(37, 99, 235, 0.25), transparent 60%),
                radial-gradient(1000px 420px at 100% 0%, rgba(6, 182, 212, 0.22), transparent 55%),
                var(--bg-main);
        }}
        .page {{ max-width: 1480px; margin: 0 auto; padding: 32px 24px 56px; }}
        .hero {{
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(15, 35, 58, 0.88));
            border: 1px solid var(--border-soft);
            border-radius: 22px;
            padding: 28px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.22);
            margin-bottom: 22px;
        }}
        .eyebrow {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 999px;
            background: var(--accent-soft);
            color: #bae6fd;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 14px;
        }}
        h1 {{ margin: 0 0 10px; font-size: 2rem; }}
        h2 {{ margin: 0 0 16px; font-size: 1.25rem; }}
        p.lead {{ margin: 0; color: var(--text-soft); line-height: 1.6; }}
        .section {{
            background: rgba(15, 27, 45, 0.92);
            border: 1px solid var(--border-soft);
            border-radius: 20px;
            padding: 22px;
            margin-top: 20px;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 14px;
            margin-top: 20px;
        }}
        .kpi-card {{
            padding: 18px;
            border-radius: 18px;
            background: linear-gradient(145deg, rgba(20, 33, 54, 0.95), rgba(13, 24, 40, 0.95));
            border: 1px solid var(--border-soft);
        }}
        .kpi-label {{
            display: block;
            color: var(--text-soft);
            font-size: 0.85rem;
            margin-bottom: 8px;
        }}
        .kpi-value {{ font-size: 1.45rem; color: #f8fbff; }}
        .summary-table {{ border-collapse: collapse; width: 100%; margin-bottom: 0; }}
        .summary-table th, .summary-table td {{
            border: 1px solid var(--border-soft);
            padding: 10px 12px;
            text-align: left;
            vertical-align: top;
        }}
        .summary-table th {{ background: rgba(148, 163, 184, 0.08); }}
        .written-report {{ padding: 4px 0 0; color: var(--text-main); }}
        .written-report section + section {{ margin-top: 18px; }}
        .written-report h3 {{ margin: 0 0 10px; }}
        .written-report ul {{ margin: 0; padding-left: 20px; color: var(--text-soft); }}
        .written-report li + li {{ margin-top: 6px; }}
        .plot-wrapper {{ margin-top: 8px; }}
        .plot-wrapper .plotly-graph-div {{ border-radius: 16px; overflow: hidden; }}
        @media (max-width: 900px) {{
            .page {{ padding: 20px 14px 36px; }}
            .hero, .section {{ padding: 18px; }}
        }}
  </style>
</head>
<body>
    <div class=\"page\">
        <section class=\"hero\">
            <span class=\"eyebrow\">Data Quality • BI Executive Report</span>
            <h1>DataSentinel - Relatorio Executivo</h1>
            <p class=\"lead\">
                Visao consolidada de qualidade, anomalias e perfil da base processada,
                preparada para leitura executiva, auditoria tecnica e compartilhamento.
            </p>
            <div class=\"kpi-grid\">{kpi_cards_html}</div>
        </section>
        <section class=\"section\">
            <h2>Resumo Executivo</h2>
            {summary_table}
        </section>
        <section class=\"section\">
            <h2>Relatorio Escrito da Planilha</h2>
            <div class=\"written-report\">{written_summary_html}</div>
        </section>
        <section class=\"section\">
            <h2>Perfil Detalhado da Base</h2>
            {profile_table}
        </section>
        <section class=\"section\">
            <h2>Problemas de Qualidade</h2>
            {quality_table}
        </section>
        <section class=\"section\">
            <h2>Anomalias Detectadas</h2>
            {anomalies_table}
        </section>
        <section class=\"section plot-wrapper\">
            <h2>Graficos Analiticos</h2>
            {chart_html}
        </section>
    </div>
</body>
</html>
"""
