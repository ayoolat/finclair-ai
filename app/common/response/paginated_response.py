import math
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool

    @classmethod
    def build(cls, page: int, page_size: int, total: int) -> "PaginationMeta":
        total_pages = math.ceil(total / page_size) if page_size else 0
        return cls(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    message: Optional[str] = None
    data: list[T]
    pagination: PaginationMeta

    @classmethod
    def ok(
        cls,
        data: list[T],
        page: int,
        page_size: int,
        total: int,
        message: Optional[str] = None,
    ) -> "PaginatedResponse[T]":
        return cls(
            success=True,
            message=message,
            data=data,
            pagination=PaginationMeta.build(page=page, page_size=page_size, total=total),
        )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        kwargs.setdefault("mode", "json")
        return super().model_dump(**kwargs)
