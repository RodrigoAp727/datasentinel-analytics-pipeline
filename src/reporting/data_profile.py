from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


def _format_value(value: Any) -> str:
    if pd.isna(value):
        return "n/d"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def build_column_profile_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for column in dataframe.columns:
        series = dataframe[column]
        non_null_series = series.dropna()
        null_count = int(series.isna().sum())
        null_ratio = (null_count / max(len(series), 1)) * 100
        unique_count = int(non_null_series.nunique())

        row: dict[str, Any] = {
            "coluna": column,
            "tipo": str(series.dtype),
            "nulos": null_count,
            "nulos_percentual": round(null_ratio, 2),
            "valores_unicos": unique_count,
            "amostra": (
                _format_value(non_null_series.iloc[0])
                if not non_null_series.empty
                else "n/d"
            ),
            "min": "n/d",
            "max": "n/d",
            "media": "n/d",
            "mediana": "n/d",
            "valor_mais_frequente": "n/d",
            "freq_mais_frequente": 0,
        }

        if pd.api.types.is_numeric_dtype(series):
            row.update(
                {
                    "min": (
                        _format_value(non_null_series.min())
                        if not non_null_series.empty
                        else "n/d"
                    ),
                    "max": (
                        _format_value(non_null_series.max())
                        if not non_null_series.empty
                        else "n/d"
                    ),
                    "media": (
                        _format_value(non_null_series.mean())
                        if not non_null_series.empty
                        else "n/d"
                    ),
                    "mediana": (
                        _format_value(non_null_series.median())
                        if not non_null_series.empty
                        else "n/d"
                    ),
                }
            )
        elif not non_null_series.empty:
            mode_series = non_null_series.mode(dropna=True)
            top_value = mode_series.iloc[0] if not mode_series.empty else non_null_series.iloc[0]
            top_frequency = int((non_null_series == top_value).sum())
            row.update(
                {
                    "valor_mais_frequente": _format_value(top_value),
                    "freq_mais_frequente": top_frequency,
                }
            )

        rows.append(row)

    return pd.DataFrame(rows)


def build_written_summary(
    dataframe: pd.DataFrame,
    quality_report: Any,
    anomaly_report: Any,
) -> str:
    total_rows = len(dataframe)
    total_columns = dataframe.shape[1]
    total_cells = max(total_rows * total_columns, 1)
    null_cells = int(dataframe.isna().sum().sum())
    null_ratio = (null_cells / total_cells) * 100
    duplicate_rows = int(dataframe.duplicated().sum())

    severity_counter = Counter(a.severity for a in anomaly_report.anomalies)
    high_anomalies = severity_counter.get("alta", 0)
    medium_anomalies = severity_counter.get("media", 0)
    low_anomalies = severity_counter.get("baixa", 0)

    summary_lines = [
        "#### Visao geral da planilha",
        f"- Status geral de qualidade: {quality_report.status}.",
        f"- Score de qualidade: {quality_report.score:.2f}.",
        (
            f"- Base recebida com {total_rows} linhas e {total_columns} colunas, "
            f"totalizando {total_cells} celulas analisadas."
        ),
        (
            f"- Foram encontrados {null_cells} valores nulos "
            f"({null_ratio:.2f}% da base) e {duplicate_rows} linhas duplicadas."
        ),
        (
            f"- Anomalias detectadas: {len(anomaly_report.anomalies)} no total "
            f"(alta={high_anomalies}, media={medium_anomalies}, baixa={low_anomalies})."
        ),
        f"- Problemas de qualidade listados: {len(quality_report.issues)}.",
    ]

    if quality_report.issues:
        main_issue = quality_report.issues[0]
        summary_lines.append(
            "- Principal alerta de qualidade: "
            f"{main_issue.check} - {main_issue.message}"
        )

    if anomaly_report.anomalies:
        first_anomaly = anomaly_report.anomalies[0]
        summary_lines.append(
            "- Primeira anomalia relevante: "
            f"coluna '{first_anomaly.column}', indice '{first_anomaly.index}', "
            f"severidade '{first_anomaly.severity}'."
        )

    summary_lines.append("")
    summary_lines.append("#### Diagnostico detalhado da planilha recebida")

    profile_df = build_column_profile_dataframe(dataframe)
    for row in profile_df.itertuples(index=False):
        column_lines = [
            (
                f"- Coluna '{row.coluna}': tipo {row.tipo}, "
                f"{row.valores_unicos} valores unicos e {row.nulos} nulos "
                f"({row.nulos_percentual:.2f}%)."
            ),
        ]

        if row.media != "n/d":
            column_lines.append(
                f"  Faixa observada entre {row.min} e {row.max}, "
                f"media {row.media} e mediana {row.mediana}."
            )
        else:
            column_lines.append(
                "  Valor mais frequente: "
                f"{row.valor_mais_frequente} "
                f"({row.freq_mais_frequente} ocorrencias)."
            )

        if row.amostra != "n/d":
            column_lines.append(f"  Exemplo de valor recebido: {row.amostra}.")

        summary_lines.extend(column_lines)

    recommendations: list[str] = []
    if null_cells > 0:
        recommendations.append(
            "Tratar nulos antes da carga produtiva, "
            "principalmente nas colunas com maior impacto analitico."
        )
    if duplicate_rows > 0:
        recommendations.append(
            "Revisar a deduplicacao da origem para evitar "
            "contagem e tendencia distorcidas."
        )
    if quality_report.issues:
        recommendations.append(
            "Ajustar as regras de qualidade ou corrigir a fonte "
            "para eliminar os alertas listados."
        )
    if anomaly_report.anomalies:
        recommendations.append(
            "Validar com a area de negocio se as anomalias sao eventos reais ou erro de captura."
        )

    if recommendations:
        summary_lines.append("")
        summary_lines.append("#### Recomendacoes para deixar a base pronta")
        summary_lines.extend(f"- {recommendation}" for recommendation in recommendations)

    return "\n".join(summary_lines)


def build_written_summary_html(
    dataframe: pd.DataFrame,
    quality_report: Any,
    anomaly_report: Any,
) -> str:
    sections: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_items: list[str] = []
    current_index = -1

    for raw_line in build_written_summary(dataframe, quality_report, anomaly_report).splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        if line.startswith("#### "):
            if current_heading is not None:
                sections.append((current_heading, current_items))
            current_heading = line.removeprefix("#### ").strip()
            current_items = []
            current_index = -1
            continue

        if line.startswith("- "):
            current_items.append(line[2:].strip())
            current_index = len(current_items) - 1
            continue

        if current_index >= 0:
            current_items[current_index] = f"{current_items[current_index]} {line.strip()}"

    if current_heading is not None:
        sections.append((current_heading, current_items))

    html_parts: list[str] = []
    for heading, items in sections:
        html_parts.append(f"<section><h3>{heading}</h3>")
        if items:
            html_parts.append("<ul>")
            html_parts.extend(f"<li>{item}</li>" for item in items)
            html_parts.append("</ul>")
        html_parts.append("</section>")

    return "".join(html_parts)