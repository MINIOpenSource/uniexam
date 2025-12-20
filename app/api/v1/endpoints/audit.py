from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.base import get_db
from app.db.models import AuditLog, User
from app.schemas.audit import AuditLogResponse
from app.services.auth import get_current_active_admin

router = APIRouter()

@router.get("/", response_model=List[AuditLogResponse])
async def read_audit_logs(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    result = await db.execute(select(AuditLog).order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit))
    return result.scalars().all()
