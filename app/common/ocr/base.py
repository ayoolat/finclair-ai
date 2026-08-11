from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class OcrItem:
    name: str
    quantity: int
    unit_price: Decimal
    category: Optional[str] = None


@dataclass
class OcrResult:
    total: Decimal
    items: list[OcrItem] = field(default_factory=list)
    merchant: Optional[str] = None
    currency: Optional[str] = None
    confidence: float = 0.0
    tax: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    category: Optional[str] = None


class OcrProvider(ABC):
    @abstractmethod
    async def parse_receipt(
        self,
        image_bytes: bytes,
        content_type: str,
        category_names: Optional[list[str]] = None,
    ) -> OcrResult:
        """Extract structured receipt data from an image.

        `category_names`, when given, is the picklist of category names the
        caller wants the model to choose from (both the overall receipt
        category and each item's category); the model is free to leave the
        category null if nothing fits.
        """
        ...
