from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, Request, Depends
from app.db.base import get_db
from app.db.models import RateLimit
from app.core.config import settings


class RateLimiterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_rate_limit(self, key: str, limit: int = settings.RATE_LIMIT_PER_MINUTE):
        result = await self.db.execute(select(RateLimit).where(RateLimit.key == key))
        record = result.scalars().first()

        now = datetime.now(timezone.utc)
        window_duration = timedelta(minutes=1)

        if not record:
            new_record = RateLimit(key=key, count=1, window_start=now)
            self.db.add(new_record)
            await self.db.commit()
            return

        window_start = record.window_start
        if window_start.tzinfo is None:
            window_start = window_start.replace(tzinfo=timezone.utc)

        if now > window_start + window_duration:
            record.window_start = now
            record.count = 1
        else:
            if record.count >= limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            record.count += 1

        await self.db.commit()


async def check_rate_limit(request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    service = RateLimiterService(db)
    await service.check_rate_limit(f"ip:{client_ip}")
