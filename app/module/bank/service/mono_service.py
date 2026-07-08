import logging
from typing import Optional

import httpx

from app.common.clients.mono_client import get_mono_async_client

logger = logging.getLogger(__name__)


def _unwrap(body: dict) -> dict:
    """Mono wraps most GET responses as {"data": {...}}; some are returned bare."""
    data = body.get("data")
    return data if isinstance(data, dict) else body


def _unwrap_account(body: dict) -> dict:
    """GET /accounts/{id} nests the account object one level further: {"data": {"account": {...}}}."""
    outer = _unwrap(body)
    account = outer.get("account")
    return account if isinstance(account, dict) else outer


class MonoService:
    def __init__(self) -> None:
        self._client = get_mono_async_client()

    async def exchange_code(self, code: str) -> tuple[Optional[str], Optional[str]]:
        """
        Exchange a one-time Mono Connect code for an account_id.
        Returns (account_id, error_message). One of the two will be None.
        """
        try:
            response = await self._client.post("/accounts/auth", json={"code": code})
            body = response.json()
            logger.info("Mono exchange_code response (%s): %s", response.status_code, body)
            if response.status_code != 200:
                error_msg = body.get("message") or body.get("error") or f"Mono returned {response.status_code}"
                logger.error("Mono exchange_code failed (%s): %s", response.status_code, body)
                return None, error_msg
            account_id = _unwrap(body).get("id")
            if not account_id:
                logger.error("Mono exchange_code returned 200 with no account id: %s", body)
                return None, "Mono did not return an account id for this code."
            return account_id, None
        except httpx.HTTPError as exc:
            logger.error("Mono exchange_code HTTP error: %s", exc)
            return None, "Could not reach Mono. Please try again."

    async def get_account(self, account_id: str) -> Optional[dict]:
        try:
            response = await self._client.get(f"/accounts/{account_id}")
            response.raise_for_status()
            return _unwrap_account(response.json())
        except Exception as exc:
            logger.error("Mono get_account failed for %s: %s", account_id, exc)
            return None

    async def get_balance(self, account_id: str) -> Optional[dict]:
        try:
            response = await self._client.get(f"/accounts/{account_id}")
            response.raise_for_status()
            data = _unwrap_account(response.json())
            return {
                "balance": data.get("balance"),
                "currency": data.get("currency", "NGN"),
                "account_number": data.get("account_number"),
                "name": data.get("name"),
            }
        except Exception as exc:
            logger.error("Mono get_balance failed for %s: %s", account_id, exc)
            return None

    async def get_transactions(self, account_id: str, since: Optional[str] = None) -> list[dict]:
        try:
            params: dict = {"paginate": "false"}
            if since:
                params["start"] = since
            response = await self._client.get(
                f"/accounts/{account_id}/transactions", params=params
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
