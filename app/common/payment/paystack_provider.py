import asyncio
from typing import Any

from app.common.clients.paystack_client import get_paystack_client
from app.common.payment.base import PaymentProvider
from app.core.config import settings


class PaystackPaymentProvider(PaymentProvider):
    @property
    def public_key(self) -> str:
        return settings.paystack_public_key

    async def verify_transaction(self, reference: str) -> dict[str, Any]:
        client = get_paystack_client()
        response = await asyncio.to_thread(client.get, f"/transaction/verify/{reference}")
        response.raise_for_status()
        return response.json()["data"]

    async def charge_authorization(
        self, *, authorization_code: str, email: str, amount: int, reference: str
    ) -> dict[str, Any]:
        client = get_paystack_client()
        response = await asyncio.to_thread(
            client.post,
            "/transaction/charge_authorization",
            json={
                "authorization_code": authorization_code,
                "email": email,
                "amount": amount,
                "reference": reference,
            },
        )
        response.raise_for_status()
        return response.json()["data"]
