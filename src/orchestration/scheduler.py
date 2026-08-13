"""Pipeline scheduler using APScheduler."""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from orchestration.pipeline import DataPipeline


class PipelineScheduler:
    """Schedule DataPipeline execution with interval or daily cron triggers."""

    def __init__(self, pipeline: DataPipeline, timezone: str = "UTC") -> None:
        self.pipeline = pipeline
        self.scheduler = BlockingScheduler(timezone=timezone)

    def start_interval(self, *, hours: int = 1, minutes: int = 0) -> None:
        """Start scheduler with interval trigger.

        Args:
            hours: Hours between executions.
            minutes: Minutes between executions.
        """
        if hours < 0 or minutes < 0:
            raise ValueError("hours and minutes must be >= 0")
        if hours == 0 and minutes == 0:
            raise ValueError("at least one of hours or minutes must be > 0")

        self.scheduler.add_job(
            self.pipeline.run,
            trigger="interval",
            hours=hours,
            minutes=minutes,
            id="datasentinel_pipeline_interval",
            replace_existing=True,
        )
        logger.info(
            "Starting scheduler with interval trigger hours={} minutes={}",
            hours,
            minutes,
        )
        self.scheduler.start()

    def start_daily_cron(self, *, hour: int = 0, minute: int = 0) -> None:
        """Start scheduler with daily cron trigger.

        Args:
            hour: Hour of day (0-23).
            minute: Minute (0-59).
        """
        if not 0 <= hour <= 23:
            raise ValueError("hour must be between 0 and 23")
        if not 0 <= minute <= 59:
            raise ValueError("minute must be between 0 and 59")

        self.scheduler.add_job(
            self.pipeline.run,
            trigger="cron",
            hour=hour,
            minute=minute,
            id="datasentinel_pipeline_daily",
            replace_existing=True,
        )
        logger.info("Starting scheduler with daily cron at {:02d}:{:02d}", hour, minute)
        self.scheduler.start()
