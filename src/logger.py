import sys
from pathlib import Path

from loguru import logger


def setup_logging() -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()

    logger.add(
        sys.stderr,
        level="INFO",
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

    logger.add(
        logs_dir / "datasentinel.log",
        rotation="00:00",
        retention="30 days",
        level="INFO",
        enqueue=True,
        serialize=True,
        backtrace=False,
        diagnose=False,
    )


setup_logging()
