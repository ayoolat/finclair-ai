from abc import ABC, abstractmethod
from typing import Any


class PaymentProvider(ABC):
    @property
    @abstractmethod
    def public_key(self) -> str:
        """Client-side key used to initialize the provider's mobile/web SDK."""
        ...

    @abstractmethod
    async def verify_transaction(self, reference: str) -> dict[str, Any]:
        """Confirm a client-side charge succeeded and return the gateway's transaction data."""
        ...

    @abstractmethod
    async def charge_authorization(
        self, *, authorization_code: str, email: str, amount: int, reference: str
    ) -> dict[str, Any]:
        """Charge a previously-authorized (tokenized) card for a new billing cycle."""
        ...
