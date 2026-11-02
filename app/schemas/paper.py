from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.db.models import PaperStatus, QuestionType


class PaperGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    question_bank_id: str
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    question_count: int = Field(default=10, ge=1, le=200)


class PaperQuestionResponse(BaseModel):
    id: str  # internal paper_question id
    question_type: QuestionType
    content: Dict[str, Any]  # Question content (body, UUID-keyed shuffled options)
    score_awarded: Optional[float]
    max_score: float
    user_answer: Optional[Dict[str, Any]]

    # For results view
    is_correct: Optional[bool]
    manual_comment: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class PaperResponse(BaseModel):
    id: str
    title: str
    status: PaperStatus
    score: Optional[float]
    total_score: float
    created_at: datetime
    submitted_at: Optional[datetime]
    paper_hash: Optional[str] = None

    questions: List[PaperQuestionResponse] = []

    model_config = ConfigDict(from_attributes=True)


class PaperSubmission(BaseModel):
    # Map of paper_question_id -> answer_dict
    answers: Dict[str, Dict[str, Any]]
    # Client must submit the issued paper questions alongside answers so server can verify hash
    questions: Optional[List[Dict[str, Any]]] = None
    paper: Optional[List[Dict[str, Any]]] = None
    paper_hash: Optional[str] = None


class GradingRequest(BaseModel):
    score: float = Field(..., ge=0.0)
    comment: Optional[str] = None
