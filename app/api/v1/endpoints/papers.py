from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
import random

from app.db.base import get_db
from app.db.models import Paper, PaperQuestion, Question, User, PaperStatus, UserRole
from app.schemas.paper import PaperGenerateRequest, PaperResponse, PaperSubmission
from app.services.auth import get_current_user
from app.services.grading import grading_service
from app.services.paper_hash import paper_issuance_service

router = APIRouter()


@router.get("/", response_model=List[PaperResponse])
async def list_my_papers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = (
        select(Paper)
        .options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question))
        .where(Paper.user_id == current_user.id)
        .order_by(Paper.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    papers = result.scalars().all()
    responses = [await _map_paper_to_response(p, db) for p in papers]
    await db.commit()
    return responses


@router.post("/generate", response_model=PaperResponse)
async def generate_paper(
    request: PaperGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = select(Question).where(Question.bank_id == request.question_bank_id)
    if request.difficulty is not None:
        stmt = stmt.where(Question.difficulty == request.difficulty)

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
        total_score=float(len(selected_questions))
    )
    db.add(paper)
    await db.flush()

    # Create PaperQuestions
    for q in selected_questions:
        pq = PaperQuestion(
            paper_id=paper.id,
            question_id=q.id,
            max_score=1.0
        )
        db.add(pq)

    await db.commit()

    stmt = select(Paper).options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question)).where(Paper.id == paper.id)
    result = await db.execute(stmt)
    paper = result.scalars().first()

    resp = await _map_paper_to_response(paper, db)
    await db.commit()
    return resp


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
    if paper.user_id != current_user.id and current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(status_code=403, detail="Not your paper")

    resp = await _map_paper_to_response(paper, db)
    await db.commit()
    return resp


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

    submitted_questions = submission.questions or submission.paper
    try:
        resolved_answers = await paper_issuance_service.verify_and_resolve_v1_submission(
            paper=paper,
            submitted_questions=submitted_questions,
            answers_map=submission.answers,
            submitted_hash=submission.paper_hash,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_score_awarded = 0.0

    for pq in paper.paper_questions:
        ans = resolved_answers.get(pq.id)

        if ans is not None:
            pq.user_answer = ans
            score_multiplier = grading_service.grade_question(pq.question, ans)
            pq.score_awarded = score_multiplier * pq.max_score
            pq.is_correct = (score_multiplier == 1.0)
            total_score_awarded += pq.score_awarded
        else:
            pq.score_awarded = 0.0
            pq.is_correct = False

    paper.status = PaperStatus.SUBMITTED
    paper.score = total_score_awarded
    paper.submitted_at = datetime.now(timezone.utc)

    resp = await _map_paper_to_response(paper, db)
    await db.commit()
    return resp


async def _map_paper_to_response(paper: Paper, db: Optional[AsyncSession] = None) -> PaperResponse:
    pqs, paper_hash = await paper_issuance_service.issue_v1_paper_questions(paper, db=db)

    return PaperResponse(
        id=paper.id,
        title=paper.title,
        status=paper.status,
        score=paper.score,
        total_score=paper.total_score,
        created_at=paper.created_at,
        submitted_at=paper.submitted_at,
        paper_hash=paper_hash,
        questions=pqs,
    )
