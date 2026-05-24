from typing import Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    status_code: int = 200

    @classmethod
    def ok(cls, data: T, status_code: int = 200) -> "Result[T]":
        return cls(success=True, data=data, status_code=status_code)

    @classmethod
    def fail(
        cls,
        error: str,
        error_code: Optional[str] = None,
        status_code: int = 400,
    ) -> "Result[T]":
        return cls(
            success=False,
            error=error,
            error_code=error_code,
            status_code=status_code,
        )

    @property
    def is_ok(self) -> bool:
        return self.success

    @property
    def is_err(self) -> bool:
        return not self.success
