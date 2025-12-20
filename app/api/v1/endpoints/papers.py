from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
import random

from app.db.base import get_db
from app.db.models import Paper, PaperQuestion, Question, User, PaperStatus
from app.schemas.paper import PaperGenerateRequest, PaperResponse, PaperSubmission
from app.services.auth import get_current_user
from app.services.grading import grading_service

router = APIRouter()

@router.post("/generate", response_model=PaperResponse)
async def generate_paper(
    request: PaperGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Select questions randomly from bank with specific difficulty
    # This is a simple random selection.
    stmt = select(Question).where(
        Question.bank_id == request.question_bank_id,
        Question.difficulty == request.difficulty
    )
    result = await db.execute(stmt)
    available_questions = result.scalars().all()

    if len(available_questions) < request.question_count:
        raise HTTPException(status_code=400, detail="Not enough questions in the bank for this criteria")

    selected_questions = random.sample(available_questions, request.question_count)

    # Create Paper
    paper = Paper(
        user_id=current_user.id,
        title=request.title,
        status=PaperStatus.PENDING,
        total_score=float(len(selected_questions)) # Assuming 1 point per question for now
    )
    db.add(paper)
    await db.flush() # Get ID

    # Create PaperQuestions
    for q in selected_questions:
        pq = PaperQuestion(
            paper_id=paper.id,
            question_id=q.id,
            max_score=1.0
        )
        db.add(pq)

    await db.commit()

    # Reload paper with questions to return
    # Use selectinload to eagerly load the relationship
    stmt = select(Paper).options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question)).where(Paper.id == paper.id)
    result = await db.execute(stmt)
    paper = result.scalars().first()

    # Construct response manually to fill question content from the joined Question
    # The Pydantic model PaperResponse expects questions list.
    # We need to map DB PaperQuestion to schema PaperQuestionResponse.
    # But wait, schema expects `content`. PaperQuestion doesn't have it, Question has it.
    # We can handle this mapping in Python or enhance the model.
    # For now, let's let Pydantic from_attributes handle it if we structure it right,
    # or just manual map. Manual map is safer here.

    return _map_paper_to_response(paper)

@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Paper).options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question)).where(Paper.id == paper_id)
    result = await db.execute(stmt)
    paper = result.scalars().first()

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.user_id != current_user.id:
         raise HTTPException(status_code=403, detail="Not your paper")

    return _map_paper_to_response(paper)

@router.post("/{paper_id}/submit", response_model=PaperResponse)
async def submit_paper(
    paper_id: str,
    submission: PaperSubmission,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Paper).options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question)).where(Paper.id == paper_id)
    result = await db.execute(stmt)
    paper = result.scalars().first()

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.user_id != current_user.id:
         raise HTTPException(status_code=403, detail="Not your paper")
    if paper.status != PaperStatus.PENDING:
        raise HTTPException(status_code=400, detail="Paper already submitted")

    total_score_awarded = 0.0

    for pq in paper.paper_questions:
        # Get answer from submission
        ans = submission.answers.get(pq.id) # Keyed by PaperQuestion ID

        if ans:
            pq.user_answer = ans
            # Auto Grade
            # We need the original question answer (private)
            # It's loaded via relationship `pq.question`

            score_multiplier = grading_service.grade_question(pq.question, ans)
            pq.score_awarded = score_multiplier * pq.max_score
            if score_multiplier == 1.0:
                pq.is_correct = True
            else:
                pq.is_correct = False

            total_score_awarded += pq.score_awarded

    paper.status = PaperStatus.SUBMITTED # Or GRADED if all auto
    paper.score = total_score_awarded
    paper.submitted_at = datetime.now(timezone.utc)

    await db.commit()
    # Do not refresh, as it might unload eager-loaded relationships.
    # Since expire_on_commit=False, the object is still valid and has our updates.
    return _map_paper_to_response(paper)

def _map_paper_to_response(paper: Paper) -> PaperResponse:
    # Helper to map SQLAlchemy object to Pydantic
    pqs = []
    for pq in paper.paper_questions:
        pqs.append({
            "id": pq.id,
            "question_type": pq.question.type,
            "content": pq.question.content,
            "score_awarded": pq.score_awarded,
            "max_score": pq.max_score,
            "user_answer": pq.user_answer,
            "is_correct": pq.is_correct,
            "manual_comment": pq.manual_comment
        })

    return PaperResponse(
        id=paper.id,
        title=paper.title,
        status=paper.status,
        score=paper.score,
        total_score=paper.total_score,
        created_at=paper.created_at,
        submitted_at=paper.submitted_at,
        questions=pqs
    )
