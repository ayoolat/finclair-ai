"""
Simple asyncio-based daily task scheduler.

`schedule_daily` tasks run once at startup, then repeat every 24 hours.
`schedule_daily_at` tasks wait until the next occurrence of a fixed local
clock time, then repeat every 24 hours from there.
"""
import asyncio
import logging
from collections.abc import Coroutine
from datetime import datetime, timedelta
from typing import Any, Callable

from app.common.timezone import APP_TZ

logger = logging.getLogger(__name__)

_DAILY_SECONDS = 86_400


async def _run_daily(name: str, task_fn: Callable[[], Coroutine[Any, Any, None]]) -> None:
    while True:
        try:
            await task_fn()
        except Exception as exc:
            logger.error("Scheduled task %r failed: %s", name, exc)
        await asyncio.sleep(_DAILY_SECONDS)


def schedule_daily(name: str, task_fn: Callable[[], Coroutine[Any, Any, None]]) -> asyncio.Task:  # type: ignore[type-arg]
    """Register a coroutine function to run every 24 hours. Call from lifespan."""
    return asyncio.create_task(_run_daily(name, task_fn), name=name)


def _seconds_until_next(hour: int, minute: int) -> float:
    now = datetime.now(APP_TZ)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _run_daily_at(name: str, hour: int, minute: int, task_fn: Callable[[], Coroutine[Any, Any, None]]) -> None:
    while True:
        await asyncio.sleep(_seconds_until_next(hour, minute))
        try:
            await task_fn()
        except Exception as exc:
            logger.error("Scheduled task %r failed: %s", name, exc)


def schedule_daily_at(
    name: str, hour: int, minute: int, task_fn: Callable[[], Coroutine[Any, Any, None]]
) -> asyncio.Task:  # type: ignore[type-arg]
    """Register a coroutine function to run once daily at a fixed Africa/Lagos clock time. Call from lifespan."""
    return asyncio.create_task(_run_daily_at(name, hour, minute, task_fn), name=name)
