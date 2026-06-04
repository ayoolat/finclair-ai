from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    async def upload(self, folder: str, file_name: str, data: bytes, content_type: str) -> str:
        """Upload bytes and return the public object key (folder/file_name)."""
        ...

    @abstractmethod
    def public_url(self, folder: str, file_name: str) -> str:
        """Build the full public URL for a stored object."""
        ...

    @abstractmethod
    async def delete(self, folder: str, file_name: str) -> None:
        """Delete an object from storage."""
        ...
