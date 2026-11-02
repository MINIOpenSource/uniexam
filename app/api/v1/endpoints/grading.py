from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.base import get_db
from app.db.models import Paper, PaperQuestion, User, PaperStatus
from app.schemas.paper import PaperResponse, GradingRequest
from app.services.auth import get_current_active_admin
from app.api.v1.endpoints.papers import _map_paper_to_response

router = APIRouter()


@router.get("/pending", response_model=List[PaperResponse])
async def list_pending_grading(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    stmt = select(Paper).options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question)).where(Paper.status == PaperStatus.SUBMITTED)
    result = await db.execute(stmt)
    papers = result.scalars().all()

    responses = [await _map_paper_to_response(p, db) for p in papers]
    await db.commit()
    return responses


@router.post("/{paper_id}/questions/{pq_id}/grade", response_model=PaperResponse)
async def manual_grade_question(
    paper_id: str,
    pq_id: str,
    grading: GradingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    stmt = select(Paper).options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question)).where(Paper.id == paper_id)
    result = await db.execute(stmt)
    paper = result.scalars().first()

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    target_pq = None
    for pq in paper.paper_questions:
        if pq.id == pq_id:
            target_pq = pq
            break

    if not target_pq:
        raise HTTPException(status_code=404, detail="Question not found in this paper")

    if grading.score < 0 or grading.score > target_pq.max_score:
        raise HTTPException(
            status_code=400,
            detail=f"Score must be between 0 and {target_pq.max_score}"
        )

    target_pq.score_awarded = grading.score
    target_pq.manual_comment = grading.comment
    target_pq.is_correct = (grading.score == target_pq.max_score)

    new_total = sum((pq.score_awarded or 0.0) for pq in paper.paper_questions)
    paper.score = new_total

    resp = await _map_paper_to_response(paper, db)
    await db.commit()
    return resp
