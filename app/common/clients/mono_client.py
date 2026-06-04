import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_MONO_BASE_URL = "https://api.withmono.com/v2"


class _MonoClientSingleton:
    _instance: Optional[httpx.Client] = None

    @classmethod
    def get(cls) -> httpx.Client:
        if cls._instance is None:
            cls._instance = httpx.Client(
                base_url=_MONO_BASE_URL,
                headers={
                    "mono-sec-key": settings.mono_secret_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return cls._instance


def get_mono_client() -> httpx.Client:
    return _MonoClientSingleton.get()
