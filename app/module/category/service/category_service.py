import uuid

from fastapi import Depends
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Result
from app.database.session import get_db
from app.module.category.dto.category import CategoryDto, CreateCategoryDto
from app.module.category.schema.category import Category


class CategoryService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_categories(self, user_id: uuid.UUID) -> Result[list[CategoryDto]]:
        result = await self._db.execute(
            select(Category)
            .where(or_(Category.user_id.is_(None), Category.user_id == user_id))
            .order_by(Category.user_id.is_(None).desc(), Category.name)
        )
        categories = [CategoryDto.model_validate(row) for row in result.scalars().all()]
        return Result.ok(categories)

    async def create_category(self, user_id: uuid.UUID, dto: CreateCategoryDto) -> Result[CategoryDto]:
        category = Category(
            user_id=user_id,
            name=dto.name,
            description=dto.description,
            icon=dto.icon,
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(category)
        try:
            await self._db.commit()
        except IntegrityError:
            await self._db.rollback()
            return Result.fail("A category with this name already exists.", error_code="CONFLICT", status_code=409)
        await self._db.refresh(category)
        return Result.ok(CategoryDto.model_validate(category), status_code=201)


def get_category_service(db: AsyncSession = Depends(get_db)) -> CategoryService:
    return CategoryService(db)
