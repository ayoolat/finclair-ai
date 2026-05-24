from typing import Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    message: Optional[str] = None
    data: Optional[T] = None

    @classmethod
    def ok(cls, data: Optional[T] = None, message: Optional[str] = None) -> "ApiResponse[T]":
        return cls(success=True, data=data, message=message)

    @classmethod
    def error(cls, message: str) -> "ApiResponse[None]":
        return cls(success=False, message=message)
