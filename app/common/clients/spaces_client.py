from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

import boto3

from app.core.config import settings


class _SpacesClientSingleton:
    _instance: Optional[object] = None

    @classmethod
    def get(cls) -> "S3Client":  # type: ignore[return]
        if cls._instance is None:
            cls._instance = boto3.client(
                "s3",
                region_name=settings.spaces_region,
                endpoint_url=settings.spaces_endpoint_url,
                aws_access_key_id=settings.spaces_key,
                aws_secret_access_key=settings.spaces_secret,
            )
        return cls._instance  # type: ignore[return-value]


def get_spaces_client() -> "S3Client":
    return _SpacesClientSingleton.get()
