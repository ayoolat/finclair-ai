from typing import Optional

from app.common.ocr.base import OcrProvider
from app.core.config import settings

_provider: Optional[OcrProvider] = None


def get_ocr_provider() -> OcrProvider:
    global _provider
    if _provider is None:
        if settings.ocr_provider == "openai":
            from app.common.ocr.openai_ocr import OpenAIOcrProvider
            _provider = OpenAIOcrProvider()
        else:
            raise ValueError(f"Unknown OCR provider: {settings.ocr_provider!r}")
    return _provider
