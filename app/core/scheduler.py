"""
Simple asyncio-based daily task scheduler.
Tasks registered here run once at startup, then repeat every 24 hours.
"""
import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Callable

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
