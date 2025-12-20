from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.base import get_db
from app.db.models import Question, QuestionBank, User
from app.schemas.question import QuestionCreate, QuestionResponse, QuestionBankCreate, QuestionBankResponse
from app.services.auth import get_current_active_admin, get_current_user

router = APIRouter()

# Question Banks
@router.post("/banks", response_model=QuestionBankResponse)
async def create_question_bank(
    bank_in: QuestionBankCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    bank = QuestionBank(**bank_in.model_dump())
    db.add(bank)
    await db.commit()
    await db.refresh(bank)
    return bank

@router.get("/banks", response_model=List[QuestionBankResponse])
async def list_question_banks(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(QuestionBank).offset(skip).limit(limit))
    return result.scalars().all()

# Questions
@router.post("/", response_model=QuestionResponse)
async def create_question(
    question_in: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    # Verify bank exists
    result = await db.execute(select(QuestionBank).where(QuestionBank.id == question_in.bank_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Question Bank not found")

    question = Question(**question_in.model_dump())
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question

@router.get("/", response_model=List[QuestionResponse])
async def list_questions(
    bank_id: str = None,
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Question)
    if bank_id:
        query = query.where(Question.bank_id == bank_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()
