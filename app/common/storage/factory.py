from typing import Optional

from app.common.storage.base import StorageProvider
from app.core.config import settings

_provider: Optional[StorageProvider] = None


def get_storage_provider() -> StorageProvider:
    global _provider
    if _provider is None:
        if settings.storage_provider == "spaces":
            from app.common.storage.spaces import DigitalOceanSpacesProvider
            _provider = DigitalOceanSpacesProvider()
        else:
            raise ValueError(f"Unknown storage provider: {settings.storage_provider!r}")
    return _provider
