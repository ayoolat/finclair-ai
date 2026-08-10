import base64
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel, field_validator, model_validator

from app.common.clients.openai_client import get_openai_client
from app.common.ocr.base import OcrItem, OcrProvider, OcrResult

logger = logging.getLogger(__name__)

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
_RECONCILIATION_TOLERANCE = Decimal("0.10")  # 10% allowed discrepancy


# ── Pydantic models for structured output ────────────────────────────────────

class _ItemSchema(BaseModel):
    name: str
    quantity: float = 1.0
    unit_price: float

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_quantity(cls, v: object) -> float:
        try:
            return float(str(v).replace("x", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return 1.0

    @field_validator("unit_price", mode="before")
    @classmethod
    def parse_price(cls, v: object) -> float:
        try:
            return float(str(v).replace(",", "").strip())
        except (ValueError, TypeError):
            return 0.0


class _ReceiptSchema(BaseModel):
    is_receipt: bool
    merchant: Optional[str] = None
    currency: Optional[str] = None
    total: float
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    discount: Optional[float] = None
    confidence: float = 0.0  # 0.0 – 1.0; model's self-assessed extraction quality
    items: list[_ItemSchema] = []

    @field_validator("total", "subtotal", "tax", "discount", mode="before")
    @classmethod
    def parse_amount(cls, v: object) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(str(v).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    @model_validator(mode="after")
    def ensure_total_positive_when_receipt(self) -> "_ReceiptSchema":
        if self.is_receipt and self.total <= 0:
            raise ValueError("Extracted total must be positive.")
        return self


_SYSTEM_PROMPT = (
    "You are a precise receipt parser for a financial application. "
    "First decide whether the image is actually a purchase receipt or invoice — an itemized proof of "
    "purchase with a merchant name and a total amount paid. If it is NOT one (e.g. a flyer, poster, "
    "screenshot of a social media post, or any other unrelated image), set is_receipt to false and leave "
    "the other fields null/empty. "
    "If it IS a receipt, set is_receipt to true and extract structured data from it matching the schema. "
    "If a field cannot be determined, use null. "
    "Set confidence to a float between 0.0 (not confident) and 1.0 (fully confident) based on image clarity and extraction quality."
)

_MAX_RETRIES = 3


class OpenAIOcrProvider(OcrProvider):

    def _validate_input(self, image_bytes: bytes, content_type: str) -> None:
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise ValueError(f"Unsupported image type: {content_type}. Allowed: {_ALLOWED_CONTENT_TYPES}")
        if len(image_bytes) > _MAX_IMAGE_BYTES:
            raise ValueError(f"Image too large ({len(image_bytes)} bytes). Max: {_MAX_IMAGE_BYTES} bytes.")

    def _reconcile(self, result: OcrResult) -> OcrResult:
        if not result.items:
            return result
        items_sum = sum(item.unit_price * item.quantity for item in result.items)
        if result.total > 0 and abs(items_sum - result.total) / result.total > _RECONCILIATION_TOLERANCE:
            logger.warning(
                "Receipt reconciliation mismatch: items_sum=%.2f, total=%.2f",
                items_sum,
                result.total,
            )
        return result

    def _call_api(self, client: OpenAI, data_url: str) -> _ReceiptSchema:
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            max_tokens=1024,
            response_format=_ReceiptSchema,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": "Parse this receipt and return the structured data."},
                    ],
                },
            ],
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("Model returned no structured output.")
        return parsed

    async def parse_receipt(self, image_bytes: bytes, content_type: str) -> OcrResult:
        self._validate_input(image_bytes, content_type)

        client = get_openai_client()
        encoded = base64.standard_b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{content_type};base64,{encoded}"

        last_exc: Optional[Exception] = None
        parsed: Optional[_ReceiptSchema] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                parsed = self._call_api(client, data_url)
                break
            except Exception as exc:
                last_exc = exc
                logger.warning("OCR attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)
        else:
            raise RuntimeError(f"Receipt OCR failed after {_MAX_RETRIES} attempts.") from last_exc

        if not parsed.is_receipt:
            # A content judgment, not a transient failure — retrying the same
            # image won't change the model's mind, so fail immediately.
            raise ValueError(
                "This doesn't look like a receipt. Please upload a clear photo of an itemized purchase receipt."
            )

        def _to_decimal(v: Optional[float]) -> Optional[Decimal]:
            if v is None:
                return None
            try:
                return Decimal(str(v))
            except InvalidOperation:
                return None

        items = [
            OcrItem(
                name=item.name,
                quantity=max(1, round(item.quantity)),
                unit_price=Decimal(str(item.unit_price)),
            )
            for item in parsed.items
        ]

        result = OcrResult(
            total=Decimal(str(parsed.total)),
            items=items,
            merchant=parsed.merchant,
            currency=parsed.currency,
            confidence=parsed.confidence,
            tax=_to_decimal(parsed.tax),
            discount=_to_decimal(parsed.discount),
        )

        logger.info(
            "Receipt parsed: merchant=%s, total=%.2f, items=%d, confidence=%.2f",
            result.merchant,
            result.total,
            len(result.items),
            result.confidence,
        )

        return self._reconcile(result)
