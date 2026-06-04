import asyncio
from functools import partial

from app.common.clients.spaces_client import get_spaces_client
from app.common.storage.base import StorageProvider
from app.core.config import settings


class DigitalOceanSpacesProvider(StorageProvider):
    def __init__(self) -> None:
        self._client = get_spaces_client()
        self._bucket = settings.spaces_bucket

    async def upload(self, folder: str, file_name: str, data: bytes, content_type: str) -> str:
        key = f"{folder}/{file_name}"
        loop = asyncio.get_event_loop()
        put = partial(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ACL="public-read",
        )
        await loop.run_in_executor(None, put)
        return key

    def public_url(self, folder: str, file_name: str) -> str:
        return f"{settings.spaces_cdn_url}/{folder}/{file_name}"

    async def delete(self, folder: str, file_name: str) -> None:
        key = f"{folder}/{file_name}"
        loop = asyncio.get_event_loop()
        delete = partial(self._client.delete_object, Bucket=self._bucket, Key=key)
        await loop.run_in_executor(None, delete)
