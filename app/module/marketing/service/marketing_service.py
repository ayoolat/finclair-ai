from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Result
from app.database.session import get_db
from app.module.marketing.dto.marketing import NewsletterSubscribeDto, WaitlistJoinDto
from app.module.marketing.schema.newsletter import NewsletterSubscriber
from app.module.marketing.schema.waitlist import WaitlistEntry


class MarketingService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def newsletter_subscribe(self, dto: NewsletterSubscribeDto) -> Result[dict]:
        existing = await self._db.execute(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == str(dto.email))
        )
        if existing.scalar_one_or_none():
            return Result.ok({"email": str(dto.email), "subscribed": False, "message": "Already subscribed."})
        subscriber = NewsletterSubscriber(email=str(dto.email), name=dto.name)
        self._db.add(subscriber)
        await self._db.commit()
        return Result.ok({"email": str(dto.email), "subscribed": True}, status_code=201)

    async def waitlist_join(self, dto: WaitlistJoinDto) -> Result[dict]:
        existing = await self._db.execute(
            select(WaitlistEntry).where(WaitlistEntry.email == str(dto.email))
        )
        if existing.scalar_one_or_none():
            return Result.ok({"email": str(dto.email), "joined": False, "message": "Already on the waitlist."})
        entry = WaitlistEntry(email=str(dto.email), name=dto.name)
        self._db.add(entry)
        await self._db.commit()
        return Result.ok({"email": str(dto.email), "joined": True}, status_code=201)


def get_marketing_service(db: AsyncSession = Depends(get_db)) -> MarketingService:
    return MarketingService(db)
