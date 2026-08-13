from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _imports() -> tuple[Any, Any, Any, Any]:
    import logger as _logger_setup  # noqa: F401
    from ingestion.data_loader import APISource, CSVSource
    from orchestration.pipeline import DataPipeline
    from orchestration.scheduler import PipelineScheduler

    return APISource, CSVSource, DataPipeline, PipelineScheduler


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DataSentinel pipeline runner")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--once", action="store_true", help="Executa o pipeline uma vez")
    mode_group.add_argument("--schedule", action="store_true", help="Inicia o scheduler")

    parser.add_argument(
        "--csv-path",
        action="append",
        default=[],
        help="Caminho de arquivo tabular local (.csv/.xlsx/.xls)",
    )
    parser.add_argument(
        "--api-url",
        action="append",
        default=[],
        help="URL de API para ingestao (pode informar multiplas vezes)",
    )
    parser.add_argument("--email-to", type=str, default=None, help="Email de destino para alertas")

    parser.add_argument(
        "--schedule-mode",
        choices=["interval", "daily"],
        default="interval",
        help="Modo do scheduler: intervalo ou diario",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="Intervalo em minutos quando schedule-mode=interval",
    )
    parser.add_argument(
        "--daily-time",
        type=str,
        default="00:00",
        help="Horario HH:MM quando schedule-mode=daily",
    )
    parser.add_argument(
        "--timezone",
        type=str,
        default="UTC",
        help="Timezone para o scheduler",
    )
    return parser.parse_args()


def _build_pipeline(args: argparse.Namespace) -> Any:
    APISource, CSVSource, DataPipeline, _ = _imports()

    csv_sources = [
        CSVSource(name=f"csv_{index + 1}", path=csv_path)
        for index, csv_path in enumerate(args.csv_path)
    ]
    api_sources = [
        APISource(name=f"api_{index + 1}", url=api_url)
        for index, api_url in enumerate(args.api_url)
    ]

    return DataPipeline(
        csv_sources=csv_sources,
        api_sources=api_sources,
        email_to=args.email_to,
    )


def _parse_daily_time(value: str) -> tuple[int, int]:
    try:
        hour_str, minute_str = value.split(":", maxsplit=1)
        return int(hour_str), int(minute_str)
    except ValueError as exc:
        raise ValueError("daily-time deve estar no formato HH:MM") from exc


def main() -> None:
    from loguru import logger

    args = _parse_args()
    pipeline = _build_pipeline(args)

    if args.once:
        result = pipeline.run()
        logger.info("Pipeline finished with success={} errors={}", result.success, result.errors)
        return

    _, _, _, PipelineScheduler = _imports()
    scheduler = PipelineScheduler(pipeline, timezone=args.timezone)
    if args.schedule_mode == "interval":
        if args.interval_minutes <= 0:
            raise ValueError("interval-minutes deve ser > 0")
        hours = args.interval_minutes // 60
        minutes = args.interval_minutes % 60
        scheduler.start_interval(hours=hours, minutes=minutes)
        return

    hour, minute = _parse_daily_time(args.daily_time)
    scheduler.start_daily_cron(hour=hour, minute=minute)


if __name__ == "__main__":
    main()
