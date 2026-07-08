import uuid

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.dto.pagination import PageQueryDto
from app.common.response import PaginatedResponse, Result
from app.database.session import get_db
from app.module.goal.dto.goal import FinancialGoalDto
from app.module.goal.schema.financial_goal import FinancialGoal


class GoalService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_goals(self, filters: PageQueryDto) -> Result[PaginatedResponse[FinancialGoalDto]]:
        total = (await self._db.execute(select(func.count()).select_from(FinancialGoal))).scalar_one()

        result = await self._db.execute(
            select(FinancialGoal).offset(filters.offset).limit(filters.page_size)
        )
        goals = [FinancialGoalDto.model_validate(row) for row in result.scalars().all()]
        return Result.ok(PaginatedResponse.ok(data=goals, page=filters.page, page_size=filters.page_size, total=total))

    async def get_by_ids(self, goal_ids: list[uuid.UUID]) -> list[FinancialGoal]:
        result = await self._db.execute(
            select(FinancialGoal).where(FinancialGoal.id.in_(goal_ids))
        )
        return list(result.scalars().all())


def get_goal_service(db: AsyncSession = Depends(get_db)) -> GoalService:
    return GoalService(db)
