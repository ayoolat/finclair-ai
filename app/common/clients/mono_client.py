from typing import Optional

import httpx

from app.core.config import settings

_MONO_BASE_URL = "https://api.withmono.com/v2"

_async_client: Optional[httpx.AsyncClient] = None


def get_mono_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            base_url=_MONO_BASE_URL,
            headers={
                "mono-sec-key": settings.mono_secret_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
    return _async_client
