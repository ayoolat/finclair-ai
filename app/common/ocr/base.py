from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class OcrItem:
    name: str
    quantity: int
    unit_price: Decimal


@dataclass
class OcrResult:
    total: Decimal
    items: list[OcrItem] = field(default_factory=list)
    merchant: Optional[str] = None
    currency: Optional[str] = None
    confidence: float = 0.0
    tax: Optional[Decimal] = None
    discount: Optional[Decimal] = None


class OcrProvider(ABC):
    @abstractmethod
    async def parse_receipt(self, image_bytes: bytes, content_type: str) -> OcrResult:
        """Extract structured receipt data from an image."""
        ...
