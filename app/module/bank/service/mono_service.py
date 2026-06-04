"""
Thin wrapper around the Mono API.
All calls are synchronous (httpx.Client) and run in the service layer —
wrap with asyncio.to_thread if called from async context.
"""
import asyncio
import logging
from typing import Optional

from app.common.clients.mono_client import get_mono_client

logger = logging.getLogger(__name__)


class MonoService:
    def __init__(self) -> None:
        self._client = get_mono_client()

    async def exchange_code(self, code: str) -> Optional[str]:
        """Exchange a one-time Mono Connect code for an account_id."""
        try:
            response = await asyncio.to_thread(
                self._client.post,
                "/accounts/auth",
                json={"code": code},
            )
            response.raise_for_status()
            return response.json().get("id")
        except Exception as exc:
            logger.error("Mono exchange_code failed: %s", exc)
            return None

    async def get_account(self, account_id: str) -> Optional[dict]:
        """Fetch Mono account details (name, account_number, institution)."""
        try:
            response = await asyncio.to_thread(
                self._client.get,
                f"/accounts/{account_id}",
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.error("Mono get_account failed for %s: %s", account_id, exc)
            return None

    async def get_transactions(
        self, account_id: str, since: Optional[str] = None
    ) -> list[dict]:
        """
        Fetch transactions from Mono for a given account.
        `since` should be an ISO date string (YYYY-MM-DD); defaults to account inception.
        """
        try:
            params: dict = {"paginate": "false"}
            if since:
                params["start"] = since
            response = await asyncio.to_thread(
                self._client.get,
                f"/accounts/{account_id}/transactions",
                params=params,
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as exc:
            logger.error("Mono get_transactions failed for %s: %s", account_id, exc)
            return []


_mono_service: Optional[MonoService] = None


def get_mono_service() -> MonoService:
    global _mono_service
    if _mono_service is None:
        _mono_service = MonoService()
    return _mono_service
