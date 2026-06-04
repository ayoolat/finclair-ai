import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_PAYSTACK_BASE_URL = "https://api.paystack.co"


class _PaystackClientSingleton:
    _instance: Optional[httpx.Client] = None

    @classmethod
    def get(cls) -> httpx.Client:
        if cls._instance is None:
            cls._instance = httpx.Client(
                base_url=_PAYSTACK_BASE_URL,
                headers={
                    "Authorization": f"Bearer {settings.paystack_secret_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return cls._instance


def get_paystack_client() -> httpx.Client:
    return _PaystackClientSingleton.get()
