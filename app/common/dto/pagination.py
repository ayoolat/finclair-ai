from pydantic import BaseModel, field_validator


class PageQueryDto(BaseModel):
    page: int = 1
    page_size: int = 20

    @field_validator("page")
    @classmethod
    def page_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Page must be at least 1.")
        return v

    @field_validator("page_size")
    @classmethod
    def page_size_in_range(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError("Page size must be between 1 and 100.")
        return v

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
