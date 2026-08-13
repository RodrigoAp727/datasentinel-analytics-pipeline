from __future__ import annotations

import importlib
import sys
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml

from reporting import build_column_profile_dataframe, build_written_summary

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEFAULT_RULES_PATH = Path("config/quality_rules.yaml")
DEFAULT_REPORTS_DIR = "reports"


def _inject_dark_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg-main: #0d1117;
                --bg-panel: #161b22;
                --bg-panel-soft: #1f2937;
                --text-main: #e6edf3;
                --text-soft: #9ba7b4;
                --accent-cyan: #22d3ee;
                --accent-blue: #3b82f6;
                --border-soft: #2f3b4b;
            }

            .stApp {
                background:
                    radial-gradient(1200px 500px at 15% -10%, #1e293b 0%, transparent 60%),
                    radial-gradient(1000px 480px at 100% 0%, #0b3a57 0%, transparent 55%),
                    var(--bg-main);
                color: var(--text-main);
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #0a0f16 0%, #111827 100%);
                border-right: 1px solid var(--border-soft);
            }

            div[data-testid="stMetric"] {
                background: linear-gradient(145deg, #131a24, #0f1620);
                border: 1px solid var(--border-soft);
                border-radius: 14px;
                padding: 10px;
            }

            .ds-hero {
                padding: 18px 20px;
                border-radius: 16px;
                border: 1px solid var(--border-soft);
                background: linear-gradient(120deg, #0f172a 0%, #11263b 55%, #183851 100%);
                box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
                margin-bottom: 14px;
            }

            .ds-hero h1 {
                margin: 0;
                color: #f8fafc;
                font-size: 1.9rem;
            }

            .ds-hero p {
                margin: 8px 0 0 0;
                color: #c5d1de;
            }

            .ds-card {
                background: linear-gradient(145deg, #141d28 0%, #0f1722 100%);
                border: 1px solid var(--border-soft);
                border-radius: 16px;
                padding: 14px 16px;
            }

            .ds-card h3 {
                margin: 0 0 6px 0;
                color: #e8f1f8;
                font-size: 1.05rem;
            }

            .ds-card p {
                margin: 0;
                color: var(--text-soft);
                font-size: 0.95rem;
                line-height: 1.45;
            }

            .ds-badge {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 6px 12px;
                border-radius: 999px;
                background: rgba(34, 211, 238, 0.12);
                border: 1px solid rgba(34, 211, 238, 0.35);
                color: #bae6fd;
                font-size: 0.8rem;
                font-weight: 600;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                margin-bottom: 14px;
            }

            .ds-panel {
                background: linear-gradient(145deg, rgba(15, 23, 42, 0.98), rgba(17, 24, 39, 0.9));
                border: 1px solid var(--border-soft);
                border-radius: 16px;
                padding: 18px 20px;
                margin-bottom: 18px;
            }

            .ds-panel p {
                margin: 0;
                color: #dbe7f4;
                line-height: 1.6;
            }

            .stButton button {
                border-radius: 10px;
                border: 1px solid #1d4ed8;
                background: linear-gradient(120deg, #1d4ed8 0%, #0369a1 100%);
                color: #eff6ff;
                font-weight: 600;
                min-height: 42px;
                box-shadow: 0 6px 16px rgba(3, 105, 161, 0.25);
            }

            .stButton button:hover {
                border-color: #38bdf8;
                filter: brightness(1.1);
            }

            div[data-testid="stDownloadButton"] button {
                border-radius: 10px;
                border: 1px solid #374151;
                background: linear-gradient(120deg, #1f2937 0%, #111827 100%);
                color: #e5e7eb;
                font-weight: 600;
                min-height: 42px;
            }

            div[data-testid="stFileUploader"] section {
                background: linear-gradient(145deg, #111a25 0%, #0f172a 100%);
                border: 1px dashed #334155;
                border-radius: 14px;
            }

            div[data-testid="stFileUploader"] button {
                border: 1px solid #0ea5e9;
                background: #0f3b57;
                color: #e0f2fe;
            }

            .stTextInput input,
            .stTextArea textarea,
            div[data-baseweb="select"] > div,
            .stMultiSelect div[data-baseweb="select"] > div,
            .stSelectbox div[data-baseweb="select"] > div {
                background: #0f172a;
                color: #e5e7eb;
                border: 1px solid #334155;
            }

            div[data-testid="stRadio"] label p,
            .stMarkdown,
            .stCaption {
                color: #d4dce6;
            }

            div[data-testid="stAlert"] {
                border-radius: 12px;
                border: 1px solid #334155;
                background: #0f172a;
            }

            .stTabs [data-baseweb="tab-list"] {
                gap: 8px;
            }

            .stTabs [data-baseweb="tab"] {
                background: #111827;
                border: 1px solid #253244;
                border-radius: 10px;
                color: #cbd5e1;
                padding: 8px 14px;
            }

            .stTabs [aria-selected="true"] {
                border-color: #0284c7;
                color: #e0f2fe;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _plotly_config() -> dict[str, Any]:
    return {
        "displayModeBar": True,
        "scrollZoom": True,
        "displaylogo": False,
        "responsive": True,
        "toImageButtonOptions": {
            "format": "png",
            "filename": "datasentinel_chart",
            "height": 720,
            "width": 1280,
            "scale": 2,
        },
        "modeBarButtonsToAdd": ["drawline", "drawopenpath", "eraseshape"],
    }


def _apply_bi_chart_style(
    figure: go.Figure,
    *,
    title: str,
    yaxis_title: str | None = None,
    xaxis_title: str | None = None,
) -> go.Figure:
    figure.update_layout(
        title={"text": title, "x": 0.02, "xanchor": "left"},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        margin={"l": 18, "r": 18, "t": 60, "b": 18},
        hoverlabel={"bgcolor": "#0f172a", "font": {"color": "#e5eef9"}},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    figure.update_xaxes(
        title=xaxis_title,
        showgrid=True,
        gridcolor="rgba(148, 163, 184, 0.14)",
        zeroline=False,
    )
    figure.update_yaxes(
        title=yaxis_title,
        showgrid=True,
        gridcolor="rgba(148, 163, 184, 0.14)",
        zeroline=False,
    )
    return figure


def _render_chart_section(
    *,
    title: str,
    figure: go.Figure,
    key: str,
    caption: str | None = None,
) -> None:
    st.markdown(f"#### {title}")
    if caption:
        st.caption(caption)
    figure.update_layout(height=460)
    st.plotly_chart(figure, width="stretch", config=_plotly_config(), key=key)


def _quality_score_gauge(score: float) -> go.Figure:
    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": " pts", "font": {"size": 30, "color": "#f8fafc"}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#cbd5e1"},
                "bar": {
                    "color": (
                        "#22c55e"
                        if score >= 90
                        else "#f59e0b"
                        if score >= 75
                        else "#ef4444"
                    )
                },
                "bgcolor": "rgba(15, 23, 42, 0.3)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 75], "color": "rgba(239, 68, 68, 0.22)"},
                    {"range": [75, 90], "color": "rgba(245, 158, 11, 0.22)"},
                    {"range": [90, 100], "color": "rgba(34, 197, 94, 0.22)"},
                ],
            },
        )
    )
    return _apply_bi_chart_style(gauge, title="Score de qualidade", yaxis_title=None)


def _anomaly_severity_dataframe(anomalies: list[Any]) -> pd.DataFrame:
    if not anomalies:
        return pd.DataFrame(
            {"severidade": ["baixa", "media", "alta"], "quantidade": [0, 0, 0]}
        )

    severity_counter = Counter(a.severity for a in anomalies)
    return pd.DataFrame(
        {
            "severidade": ["baixa", "media", "alta"],
            "quantidade": [
                severity_counter.get("baixa", 0),
                severity_counter.get("media", 0),
                severity_counter.get("alta", 0),
            ],
        }
    )


def _anomalies_detail_dataframe(anomalies: list[Any]) -> pd.DataFrame:
    if not anomalies:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "coluna": anomaly.column,
                "indice": anomaly.index,
                "severidade": anomaly.severity,
                "metodo": anomaly.method,
                "valor": anomaly.value,
                "score": anomaly.score,
                "mensagem": anomaly.message,
            }
            for anomaly in anomalies
        ]
    )


def _missing_matrix_dataframe(dataframe: pd.DataFrame, max_rows: int = 40) -> pd.DataFrame:
    sample_df = dataframe.head(max_rows).copy()
    sample_df.index = [f"Linha {index}" for index in sample_df.index]
    missing_matrix = sample_df.isna().astype(int)
    return missing_matrix


def _anomaly_column_summary_dataframe(anomalies: list[Any]) -> pd.DataFrame:
    if not anomalies:
        return pd.DataFrame(
            {
                "coluna": ["sem_anomalias"],
                "severidade": ["baixa"],
                "quantidade": [0],
            }
        )

    anomaly_df = _anomalies_detail_dataframe(anomalies)
    summary_df = (
        anomaly_df.groupby(["coluna", "severidade"], dropna=False)
        .size()
        .reset_index(name="quantidade")
        .sort_values(["quantidade", "coluna"], ascending=[False, True])
    )
    return summary_df


def _categorical_candidates(dataframe: pd.DataFrame) -> list[str]:
    return [
        column
        for column in dataframe.columns
        if dataframe[column].dtype == "object" or str(dataframe[column].dtype).startswith("string")
    ]


def _imports() -> tuple[Any, Any, Any, Any]:
    anomaly_module = importlib.import_module("analysis.anomaly_detector")
    ingestion_module = importlib.import_module("ingestion.data_loader")
    reporting_module = importlib.import_module("reporting.report_generator")
    validation_module = importlib.import_module("validation.quality_checker")

    return (
        anomaly_module.AnomalyDetector,
        ingestion_module.DataLoader,
        reporting_module.ReportGenerator,
        validation_module.DataQualityChecker,
    )


def _default_quality_rules() -> dict[str, Any]:
    return {
        "required_columns": ["id", "value"],
        "null_threshold": 0.2,
        "duplicate_ratio_threshold": 0.0,
        "expected_types": {
            "id": "int",
            "value": "float",
            "category": "string",
        },
        "outlier_detection": {
            "method": "iqr",
            "max_outlier_ratio": 0.05,
            "zscore_threshold": 3.0,
            "columns": ["value"],
        },
    }


def _load_quality_rules(rules_path: Path) -> dict[str, Any]:
    if not rules_path.exists():
        return _default_quality_rules()

    try:
        content = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return _default_quality_rules()

    if not isinstance(content, dict):
        return _default_quality_rules()
    return content


def _build_sidebar_settings() -> tuple[Path, str]:
    st.sidebar.header("Configuracoes")

    rules_path_str = st.sidebar.text_input(
        "Arquivo de regras (YAML)",
        value=str(DEFAULT_RULES_PATH),
    )
    reports_dir = st.sidebar.text_input(
        "Pasta de saida dos relatorios",
        value=DEFAULT_REPORTS_DIR,
    )

    rules_path = Path(rules_path_str)
    if "rules_yaml_text" not in st.session_state:
        initial_rules = _load_quality_rules(rules_path)
        st.session_state["rules_yaml_text"] = yaml.safe_dump(
            initial_rules,
            allow_unicode=False,
            sort_keys=False,
        )

    st.sidebar.caption("Edite as regras de qualidade e salve sem sair da tela.")
    st.session_state["rules_yaml_text"] = st.sidebar.text_area(
        "Regras de qualidade (YAML)",
        value=st.session_state["rules_yaml_text"],
        height=320,
    )

    save_col, reset_col = st.sidebar.columns(2)
    with save_col:
        if st.button("Salvar Regras", width="stretch"):
            try:
                parsed = yaml.safe_load(st.session_state["rules_yaml_text"]) or {}
                if not isinstance(parsed, dict):
                    raise ValueError("YAML deve conter um objeto no nivel raiz")
                rules_path.parent.mkdir(parents=True, exist_ok=True)
                rules_path.write_text(
                    yaml.safe_dump(parsed, allow_unicode=False, sort_keys=False),
                    encoding="utf-8",
                )
                st.sidebar.success("Regras salvas com sucesso")
            except Exception as exc:
                st.sidebar.error(f"Falha ao salvar regras: {exc}")

    with reset_col:
        if st.button("Restaurar Padrao", width="stretch"):
            default_rules = _default_quality_rules()
            st.session_state["rules_yaml_text"] = yaml.safe_dump(
                default_rules,
                allow_unicode=False,
                sort_keys=False,
            )
            st.sidebar.info("Regras padrao carregadas na edicao")

    return rules_path, reports_dir


def _save_uploaded_file(uploaded_file: Any) -> Path:
    suffix = Path(uploaded_file.name).suffix.lower()
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        return Path(tmp_file.name)


def _list_excel_sheets(file_path: Path) -> list[str]:
    if file_path.suffix.lower() not in {".xlsx", ".xls"}:
        return []
    with pd.ExcelFile(file_path) as workbook:
        return list(workbook.sheet_names)


def _quality_issues_dataframe(quality_report: Any) -> pd.DataFrame:
    if not quality_report.issues:
        return pd.DataFrame([{"mensagem": "Nenhum problema de qualidade detectado."}])

    return pd.DataFrame(
        [
            {
                "check": issue.check,
                "severity": issue.severity,
                "message": issue.message,
                "affected_columns": ", ".join(issue.affected_columns),
                "details": str(issue.details),
            }
            for issue in quality_report.issues
        ]
    )


def _anomalies_dataframe(anomaly_report: Any) -> pd.DataFrame:
    if not anomaly_report.anomalies:
        return pd.DataFrame([{"mensagem": "Nenhuma anomalia detectada."}])

    return pd.DataFrame(
        [
            {
                "coluna": anomaly.column,
                "indice": anomaly.index,
                "severidade": anomaly.severity,
                "metodo": anomaly.method,
                "valor": anomaly.value,
                "score": anomaly.score,
                "mensagem": anomaly.message,
            }
            for anomaly in anomaly_report.anomalies
        ]
    )


def _build_analysis_payload(
    uploaded_file: Any,
    *,
    selected_sheet: str | None = None,
    rules_path: Path,
    reports_dir: str,
) -> dict[str, Any] | None:
    temp_path = _save_uploaded_file(uploaded_file)

    try:
        AnomalyDetector, DataLoader, ReportGenerator, DataQualityChecker = _imports()
        loader = DataLoader()
        read_kwargs: dict[str, Any] = {}
        if selected_sheet:
            read_kwargs["sheet_name"] = selected_sheet

        dataframe = loader.load_csv(temp_path, **read_kwargs)

        if dataframe.empty:
            st.warning("O arquivo foi carregado, mas nao possui linhas para analise.")
            return None

        checker = DataQualityChecker(dataframe, rules_path=rules_path)
        quality_report = checker.run_all_checks()

        detector = AnomalyDetector(dataframe)
        anomaly_report = detector.detect_across_columns()

        report_generator = ReportGenerator(
            dataframe=dataframe,
            quality_report=quality_report,
            anomaly_report=anomaly_report,
            reports_dir=reports_dir,
        )
        report_paths = report_generator.generate_reports()
        return {
            "dataframe": dataframe,
            "quality_report": quality_report,
            "anomaly_report": anomaly_report,
            "report_paths": report_paths,
            "excel_bytes": Path(report_paths["excel"]).read_bytes(),
            "html_bytes": Path(report_paths["html"]).read_bytes(),
        }
    except Exception as exc:
        st.error("Falha ao processar o arquivo. Verifique o formato e as colunas esperadas.")
        st.exception(exc)
        return None
    finally:
        temp_path.unlink(missing_ok=True)


def _render_pipeline_results(payload: dict[str, Any]) -> None:
    dataframe = payload["dataframe"]
    quality_report = payload["quality_report"]
    anomaly_report = payload["anomaly_report"]
    report_paths = payload["report_paths"]
    column_profile_df = build_column_profile_dataframe(dataframe)
    numeric_df = dataframe.select_dtypes(include="number")
    categorical_columns = _categorical_candidates(dataframe)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", quality_report.status)
    c2.metric("Score de Qualidade", f"{quality_report.score:.2f}")
    c3.metric("Problemas", len(quality_report.issues))
    c4.metric("Anomalias", len(anomaly_report.anomalies))

    st.subheader("Resumo Executivo Escrito")
    st.markdown(build_written_summary(dataframe, quality_report, anomaly_report))

    st.subheader("Relatorio Detalhado da Planilha Recebida")
    st.dataframe(column_profile_df, width="stretch")

    st.subheader("Graficos")

    control_col1, control_col2, control_col3, control_col4 = st.columns(4)
    with control_col1:
        selected_column_mode = st.selectbox(
            "Modo de tendencia",
            options=["Linha", "Area"],
            index=0,
            key="chart_mode",
        )
    with control_col2:
        histogram_bins = st.slider(
            "Quantidade de bins",
            min_value=8,
            max_value=60,
            value=24,
            step=2,
            key="hist_bins",
        )
    with control_col3:
        selected_severities = st.multiselect(
            "Severidades visiveis",
            options=["baixa", "media", "alta"],
            default=["baixa", "media", "alta"],
            key="severity_filter",
        )
    with control_col4:
        moving_average_window = st.slider(
            "Janela da media movel",
            min_value=2,
            max_value=max(2, min(12, len(dataframe))),
            value=min(4, max(2, len(dataframe))),
            step=1,
            key="moving_average_window",
        )

    st.caption(
        "Painel interativo: use zoom, selecao, hover, fullscreen e exportacao em alta resolucao "
        "para analise executiva e apresentacoes."
    )

    selected_column: str | None = None
    if not numeric_df.empty:
        selected_column = st.selectbox(
            "Metrica principal para tendencia e distribuicao",
            options=list(numeric_df.columns),
            key="pipeline_numeric_column",
        )

    category_focus_column: str | None = None
    if categorical_columns:
        category_options = ["Nenhuma"] + categorical_columns
        selected_category = st.selectbox(
            "Segmentacao categorica",
            options=category_options,
            index=0,
            key="pipeline_category_column",
        )
        if selected_category != "Nenhuma":
            category_focus_column = selected_category

    selected_severity_set = set(selected_severities)
    filtered_anomalies = [
        anomaly
        for anomaly in anomaly_report.anomalies
        if anomaly.severity in selected_severity_set
    ]

    trend_fig: go.Figure | None = None
    dist_fig: go.Figure | None = None
    segment_fig: go.Figure | None = None
    distribution_fig: go.Figure | None = None
    corr_fig: go.Figure | None = None
    completeness_fig: go.Figure | None = None
    scatter_fig: go.Figure | None = None

    null_percent = (dataframe.isna().mean() * 100).round(2).sort_values(ascending=False)
    null_fig = px.bar(
        x=null_percent.index,
        y=null_percent.values,
        labels={"x": "Coluna", "y": "% de nulos"},
        template="plotly_dark",
        color=null_percent.values,
        color_continuous_scale="Sunset",
    )
    null_fig.update_traces(
        text=null_percent.values,
        texttemplate="%{text:.2f}%",
        hovertemplate="Coluna=%{x}<br>Nulos=%{y:.2f}%<extra></extra>",
    )
    _apply_bi_chart_style(
        null_fig,
        title="Mapa de criticidade de nulos por coluna",
        xaxis_title="Colunas",
        yaxis_title="% de nulos",
    )

    severity_df = _anomaly_severity_dataframe(filtered_anomalies)
    severity_fig = px.bar(
        severity_df,
        x="severidade",
        y="quantidade",
        color="severidade",
        template="plotly_dark",
        color_discrete_map={"baixa": "#10b981", "media": "#f59e0b", "alta": "#ef4444"},
    )
    severity_fig.update_traces(
        text=severity_df["quantidade"],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="Severidade=%{x}<br>Ocorrencias=%{y}<extra></extra>",
    )
    max_count = int(severity_df["quantidade"].max())
    severity_fig.update_yaxes(range=[0, max(1, max_count + 1)], dtick=1)
    _apply_bi_chart_style(
        severity_fig,
        title="Distribuicao de anomalias por severidade",
        xaxis_title="Severidade",
        yaxis_title="Quantidade",
    )

    anomaly_column_df = _anomaly_column_summary_dataframe(filtered_anomalies)
    anomaly_column_fig = px.bar(
        anomaly_column_df,
        x="coluna",
        y="quantidade",
        color="severidade",
        barmode="stack",
        template="plotly_dark",
        color_discrete_map={
            "baixa": "#10b981",
            "media": "#f59e0b",
            "alta": "#ef4444",
        },
    )
    anomaly_column_fig.update_traces(
        hovertemplate="Coluna=%{x}<br>Quantidade=%{y}<br>Severidade=%{fullData.name}<extra></extra>"
    )
    _apply_bi_chart_style(
        anomaly_column_fig,
        title="Concentracao de anomalias por coluna",
        xaxis_title="Coluna",
        yaxis_title="Ocorrencias",
    )

    anomalies_df = _anomalies_detail_dataframe(filtered_anomalies)
    if not anomalies_df.empty:
        anomalies_df["valor_numerico"] = pd.to_numeric(
            anomalies_df["valor"],
            errors="coerce",
        )
        scatter_fig = px.scatter(
            anomalies_df,
            x="indice",
            y="valor_numerico",
            color="severidade",
            size="score",
            symbol="metodo",
            hover_data=["coluna", "mensagem"],
            template="plotly_dark",
            color_discrete_map={
                "baixa": "#10b981",
                "media": "#f59e0b",
                "alta": "#ef4444",
            },
        )
        scatter_fig.update_traces(
            hovertemplate=(
                "Indice=%{x}<br>Valor=%{y:.2f}<br>"
                "Severidade=%{marker.color}<extra></extra>"
            )
        )
        _apply_bi_chart_style(
            scatter_fig,
            title="Mapa de anomalias por registro e impacto",
            xaxis_title="Indice do registro",
            yaxis_title="Valor observado",
        )

    if selected_column is not None:
        trend_base_df = pd.DataFrame(
            {
                "indice": list(numeric_df.index),
                "valor": numeric_df[selected_column],
            }
        )
        trend_base_df["media_movel"] = (
            trend_base_df["valor"]
            .rolling(window=moving_average_window, min_periods=1)
            .mean()
        )

        if selected_column_mode == "Area":
            trend_fig = px.area(
                trend_base_df,
                x="indice",
                y="valor",
                labels={"indice": "Indice", "valor": selected_column},
                template="plotly_dark",
            )
        else:
            trend_fig = px.line(
                trend_base_df,
                x="indice",
                y="valor",
                labels={"indice": "Indice", "valor": selected_column},
                template="plotly_dark",
                markers=True,
            )
        trend_fig.add_trace(
            go.Scatter(
                x=trend_base_df["indice"],
                y=trend_base_df["media_movel"],
                mode="lines",
                name="Media movel",
                line={"color": "#f59e0b", "width": 3, "dash": "dash"},
            )
        )
        trend_fig.update_layout(hovermode="x unified")
        trend_fig.update_traces(
            hovertemplate="Indice=%{x}<br>Valor=%{y:.2f}<extra></extra>"
        )
        _apply_bi_chart_style(
            trend_fig,
            title=f"Tendencia executiva da metrica {selected_column}",
            xaxis_title="Indice do registro",
            yaxis_title=selected_column,
        )

        dist_fig = px.histogram(
            trend_base_df,
            x="valor",
            nbins=histogram_bins,
            marginal="box",
            template="plotly_dark",
            color_discrete_sequence=["#38bdf8"],
        )
        dist_fig.update_layout(bargap=0.08, hovermode="x")
        dist_fig.update_traces(hovertemplate="Faixa=%{x}<br>Volume=%{y}<extra></extra>")
        _apply_bi_chart_style(
            dist_fig,
            title=f"Distribuicao e dispersao de {selected_column}",
            xaxis_title=selected_column,
            yaxis_title="Frequencia",
        )

        if category_focus_column is not None:
            segment_df = (
                dataframe.groupby(category_focus_column, dropna=False)[selected_column]
                .agg(["mean", "median", "count"])
                .reset_index()
                .sort_values("mean", ascending=False)
            )
            segment_fig = px.bar(
                segment_df,
                x=category_focus_column,
                y="mean",
                color="count",
                text="median",
                template="plotly_dark",
                color_continuous_scale="Blues",
            )
            segment_fig.update_traces(
                texttemplate="Mediana=%{text:.2f}",
                hovertemplate=(
                    f"{category_focus_column}=%{{x}}<br>Media=%{{y:.2f}}<br>"
                    "Contagem=%{marker.color}<extra></extra>"
                ),
            )
            _apply_bi_chart_style(
                segment_fig,
                title=f"Benchmark por segmento para {selected_column}",
                xaxis_title=category_focus_column,
                yaxis_title="Media",
            )

            distribution_fig = px.box(
                dataframe,
                x=category_focus_column,
                y=selected_column,
                color=category_focus_column,
                points="all",
                template="plotly_dark",
            )
            distribution_fig.update_traces(
                jitter=0.35,
                pointpos=0,
                hovertemplate=(
                    f"{category_focus_column}=%{{x}}<br>{selected_column}=%{{y:.2f}}"
                    "<extra></extra>"
                ),
            )
            _apply_bi_chart_style(
                distribution_fig,
                title=f"Dispersao por segmento para {selected_column}",
                xaxis_title=category_focus_column,
                yaxis_title=selected_column,
            )

    if numeric_df.shape[1] > 1:
        corr_df = numeric_df.corr(numeric_only=True).round(2)
        corr_fig = px.imshow(
            corr_df,
            text_auto=True,
            aspect="auto",
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            template="plotly_dark",
        )
        corr_fig.update_traces(
            hovertemplate="Linha=%{y}<br>Coluna=%{x}<br>Correlacao=%{z:.2f}<extra></extra>"
        )
        _apply_bi_chart_style(
            corr_fig,
            title="Mapa de correlacao entre metricas numericas",
            xaxis_title="Metricas",
            yaxis_title="Metricas",
        )

    missing_matrix = _missing_matrix_dataframe(dataframe)
    completeness_fig = px.imshow(
        missing_matrix,
        aspect="auto",
        color_continuous_scale=["#0f766e", "#ef4444"],
        template="plotly_dark",
    )
    completeness_fig.update_traces(
        hovertemplate=(
            "Registro=%{y}<br>Coluna=%{x}<br>"
            "Status=%{z}<extra></extra>"
        )
    )
    completeness_fig.update_coloraxes(
        colorbar_title="0=ok | 1=nulo",
        cmin=0,
        cmax=1,
    )
    _apply_bi_chart_style(
        completeness_fig,
        title="Heatmap de completude da base amostrada",
        xaxis_title="Colunas",
        yaxis_title="Registros",
    )

    st.markdown("### Qualidade da Base")
    _render_chart_section(
        title="Score de qualidade",
        figure=_quality_score_gauge(quality_report.score),
        key="quality_gauge_chart",
        caption="Visao sintetica da saude geral da base no intervalo de 0 a 100.",
    )
    _render_chart_section(
        title="Mapa de criticidade de nulos",
        figure=null_fig,
        key="quality_null_chart",
        caption="Percentual de dados faltantes por coluna para priorizacao de correcao.",
    )
    _render_chart_section(
        title="Heatmap de completude",
        figure=completeness_fig,
        key="quality_completeness_chart",
        caption="Cada celula representa um registro e coluna; facilita localizar blocos de falha.",
    )
    if corr_fig is not None:
        _render_chart_section(
            title="Correlacao entre metricas numericas",
            figure=corr_fig,
            key="quality_correlation_chart",
            caption="Relacionamentos fortes podem indicar redundancia ou variaveis explicativas.",
        )

    st.markdown("### Risco e Anomalias")
    _render_chart_section(
        title="Distribuicao de anomalias por severidade",
        figure=severity_fig,
        key="risk_severity_chart",
        caption="Mostra o volume de eventos de baixa, media e alta severidade.",
    )
    _render_chart_section(
        title="Concentracao de anomalias por coluna",
        figure=anomaly_column_fig,
        key="risk_anomaly_column_chart",
        caption="Aponta colunas com maior recorrencia para foco de investigacao.",
    )
    if scatter_fig is not None:
        _render_chart_section(
            title="Mapa de anomalias por registro",
            figure=scatter_fig,
            key="risk_scatter_chart",
            caption="Cruza indice e valor para destacar pontos extremos e impactos.",
        )
    else:
        st.info("Nenhuma anomalia ficou visivel com o filtro atual de severidade.")

    st.markdown("### Tendencia e Distribuicao")
    if selected_column is None:
        st.info("Nao ha colunas numericas disponiveis para construir a visao analitica.")
    else:
        if trend_fig is not None:
            _render_chart_section(
                title=f"Tendencia executiva de {selected_column}",
                figure=trend_fig,
                key="detail_trend_chart",
                caption="Serie temporal por indice com media movel para leitura de padrao.",
            )
        if dist_fig is not None:
            _render_chart_section(
                title=f"Distribuicao de {selected_column}",
                figure=dist_fig,
                key="detail_distribution_chart",
                caption="Histograma com boxplot para visualizar assimetria e dispersao.",
            )

        if category_focus_column is not None:
            if segment_fig is not None:
                _render_chart_section(
                    title=f"Benchmark por segmento: {category_focus_column}",
                    figure=segment_fig,
                    key="detail_segment_chart",
                    caption="Compara media e mediana da metrica entre grupos categoricos.",
                )
            if distribution_fig is not None:
                _render_chart_section(
                    title=f"Dispersao por segmento: {category_focus_column}",
                    figure=distribution_fig,
                    key="detail_segment_distribution_chart",
                    caption="Mostra variabilidade e outliers por grupo para diagnostico fino.",
                )
        else:
            st.info(
                "Selecione uma segmentacao categorica para exibir "
                "o benchmark e a dispersao por grupo."
            )

    st.subheader("Detalhamento")
    st.markdown("**Problemas de qualidade**")
    st.dataframe(_quality_issues_dataframe(quality_report), width="stretch")

    st.markdown("**Anomalias detectadas**")
    if filtered_anomalies:
        st.dataframe(_anomalies_detail_dataframe(filtered_anomalies), width="stretch")
    else:
        st.info("Nenhuma anomalia para as severidades selecionadas.")

    st.markdown("**Amostra dos dados recebidos**")
    st.dataframe(dataframe.head(20), width="stretch")

    st.subheader("Arquivos gerados")
    st.write(f"Excel: {report_paths['excel']}")
    st.write(f"HTML: {report_paths['html']}")

    st.download_button(
        "Baixar Relatorio Excel",
        data=payload["excel_bytes"],
        file_name=Path(report_paths["excel"]).name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "Baixar Relatorio HTML",
        data=payload["html_bytes"],
        file_name=Path(report_paths["html"]).name,
        mime="text/html",
    )


def _render_modern_screen(payload: dict[str, Any] | None) -> None:
    st.markdown(
        """
        <div class="ds-hero">
            <h1>Painel Executivo</h1>
            <p>Uma visao de alto impacto para leitura rapida de risco, qualidade e anomalias.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if payload is None:
        st.info("Execute a analise na tela 'Pipeline' para preencher o painel moderno.")
        return

    dataframe = payload["dataframe"]
    quality_report = payload["quality_report"]
    anomaly_report = payload["anomaly_report"]

    total_rows = len(dataframe)
    total_cols = dataframe.shape[1]
    null_ratio = (dataframe.isna().sum().sum() / max(total_rows * total_cols, 1)) * 100
    severity_counter = Counter(a.severity for a in anomaly_report.anomalies)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Linhas", f"{total_rows:,}".replace(",", "."))
    m2.metric("Colunas", total_cols)
    m3.metric("Nulos (%)", f"{null_ratio:.2f}")
    m4.metric("Risco Alto", severity_counter.get("alta", 0))

    c1, c2, c3 = st.columns(3)
    c1.markdown(
        f"""
        <div class="ds-card">
            <h3>Status de Qualidade</h3>
            <p>
                <strong>{quality_report.status}</strong>
                com score <strong>{quality_report.score:.2f}</strong>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c2.markdown(
        f"""
        <div class="ds-card">
            <h3>Problemas Detectados</h3>
            <p>
                Total de <strong>{len(quality_report.issues)}</strong>
                alertas de qualidade catalogados.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c3.markdown(
        f"""
        <div class="ds-card">
            <h3>Anomalias</h3>
            <p>
                Foram encontradas <strong>{len(anomaly_report.anomalies)}</strong>
                ocorrencias no conjunto.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Visao de severidade")
    severity_counts = [
        severity_counter.get("baixa", 0),
        severity_counter.get("media", 0),
        severity_counter.get("alta", 0),
    ]
    total_anomalies = sum(severity_counts)
    severity_df = pd.DataFrame(
        {
            "severidade": ["baixa", "media", "alta"],
            "quantidade": severity_counts,
        }
    )
    if total_anomalies == 0:
        st.info(
            "Nenhuma anomalia detectada nesta execucao. "
            "O grafico de risco aparece apos detectar ocorrencias."
        )
    else:
        donut = px.pie(
            severity_df,
            names="severidade",
            values="quantidade",
            hole=0.58,
            template="plotly_dark",
            color="severidade",
            color_discrete_map={"baixa": "#10b981", "media": "#f59e0b", "alta": "#ef4444"},
        )
        donut.update_layout(title="Composicao de risco", showlegend=True)
        st.plotly_chart(donut, width="stretch", config=_plotly_config())

    st.markdown("### Resumo escrito")
    st.markdown(build_written_summary(dataframe, quality_report, anomaly_report))


def main() -> None:
    st.set_page_config(
        page_title="DataSentinel - Gerador de Relatorio",
        page_icon="📊",
        layout="wide",
    )

    _inject_dark_theme()

    st.markdown(
        """
        <div class="ds-hero">
            <div class="ds-badge">Data quality • anomaly detection • executive reporting</div>
            <h1>DataSentinel</h1>
            <p>
                Automacao de pipeline analitico com leitura tabular,
                validacao, deteccao de anomalias e relatorios executivos.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="ds-panel">
            <p>
                Envie um arquivo .csv, .xlsx ou .xls para executar ingestao, validacao,
                analise de risco e geracao de artefatos prontos para decisao executiva.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rules_path, reports_dir = _build_sidebar_settings()
    page = st.sidebar.radio("Navegacao", ["Pipeline", "Painel Moderno"])

    payload = st.session_state.get("analysis_payload")

    if page == "Painel Moderno":
        _render_modern_screen(payload)
        return

    st.info(
        "Carregue um arquivo de dados em .csv, .xlsx ou .xls e clique em 'Gerar Relatorio' "
        "para executar ingestao, validacao, analise de risco e producao dos artefatos."
    )

    uploaded_file = st.file_uploader(
        "Selecione o arquivo de entrada",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=False,
    )

    if uploaded_file is None:
        st.stop()

    st.write(
        f"Arquivo carregado: {uploaded_file.name} "
        f"({uploaded_file.size} bytes)"
    )

    selected_sheet: str | None = None
    extension = Path(uploaded_file.name).suffix.lower()
    if extension in {".xlsx", ".xls"}:
        temp_path = _save_uploaded_file(uploaded_file)
        try:
            sheet_names = _list_excel_sheets(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        if sheet_names:
            selected_sheet = st.selectbox(
                "Selecione a aba da planilha",
                options=sheet_names,
                index=0,
            )

    if st.button("Gerar Relatorio", type="primary"):
        with st.spinner("Executando pipeline e gerando relatorios..."):
            payload = _build_analysis_payload(
                uploaded_file,
                selected_sheet=selected_sheet,
                rules_path=rules_path,
                reports_dir=reports_dir,
            )
            if payload is not None:
                st.session_state["analysis_payload"] = payload
                st.success(
                    "Relatorio gerado com sucesso. Acesse tambem a tela "
                    "'Painel Moderno' na barra lateral."
                )

    payload = st.session_state.get("analysis_payload")
    if payload is not None:
        _render_pipeline_results(payload)


if __name__ == "__main__":
    main()
