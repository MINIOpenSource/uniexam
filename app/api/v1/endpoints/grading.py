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
    # Find papers that are submitted but not fully graded?
    # For simplicity, let's say "SUBMITTED" state implies pending manual review if needed.
    # Or we can check if any question has manual grading needed.

    stmt = select(Paper).options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question)).where(Paper.status == PaperStatus.SUBMITTED)
    result = await db.execute(stmt)
    papers = result.scalars().all()

    return [_map_paper_to_response(p) for p in papers]

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

    # Update score
    target_pq.score_awarded = grading.score
    target_pq.manual_comment = grading.comment
    target_pq.is_correct = (grading.score == target_pq.max_score) # Simple logic

    # Recalculate total
    new_total = sum((pq.score_awarded or 0.0) for pq in paper.paper_questions)
    paper.score = new_total

    # Check if all graded (optional logic)
    # paper.status = PaperStatus.GRADED

    await db.commit()
    # Do not refresh to preserve loaded relationships
    return _map_paper_to_response(paper)
