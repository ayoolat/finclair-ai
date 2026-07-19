from typing import Optional

from app.common.payment.base import PaymentProvider
from app.core.config import settings

_provider: Optional[PaymentProvider] = None


def get_payment_provider() -> PaymentProvider:
    global _provider
    if _provider is None:
        if settings.payment_provider == "paystack":
            from app.common.payment.paystack_provider import PaystackPaymentProvider
            _provider = PaystackPaymentProvider()
        else:
            raise ValueError(f"Unknown payment provider: {settings.payment_provider!r}")
    return _provider
