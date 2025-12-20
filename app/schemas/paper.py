from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.db.models import PaperStatus, QuestionType

class PaperGenerateRequest(BaseModel):
    title: str
    question_bank_id: str
    difficulty: int = 1
    question_count: int = 10

class PaperQuestionResponse(BaseModel):
    id: str # internal paper_question id
    question_type: QuestionType
    content: Dict[str, Any] # Question content (body, options)
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

    questions: List[PaperQuestionResponse] = []

    model_config = ConfigDict(from_attributes=True)

class PaperSubmission(BaseModel):
    # Map of paper_question_id -> answer_dict
    answers: Dict[str, Dict[str, Any]]

class GradingRequest(BaseModel):
    score: float
    comment: Optional[str] = None
