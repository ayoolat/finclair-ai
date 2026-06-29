import uuid
from datetime import date
from typing import Optional

from fastapi import Depends

from app.common.response import Result
from app.module.insight.dto.insight import HomeInsightDto
from app.module.insight.service.clara_service import ClaraService, get_clara_service


class InsightService:
    def __init__(self, clara: ClaraService) -> None:
        self._clara = clara

    async def home_insight(
        self,
        user_id: uuid.UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Result[HomeInsightDto]:
        return await self._clara.home_insight(user_id, start_date, end_date)


def get_insight_service(
    clara: ClaraService = Depends(get_clara_service),
) -> InsightService:
    return InsightService(clara)
