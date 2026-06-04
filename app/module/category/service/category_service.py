from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Result
from app.database.session import get_db
from app.module.category.dto.category import CategoryDto
from app.module.category.schema.category import Category


class CategoryService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_categories(self) -> Result[list[CategoryDto]]:
        result = await self._db.execute(select(Category).order_by(Category.name))
        categories = [CategoryDto.model_validate(row) for row in result.scalars().all()]
        return Result.ok(categories)


def get_category_service(db: AsyncSession = Depends(get_db)) -> CategoryService:
    return CategoryService(db)
