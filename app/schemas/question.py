from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.db.models import QuestionType

class QuestionBase(BaseModel):
    type: QuestionType
    content: Dict[str, Any]
    difficulty: int = 1

class QuestionCreate(QuestionBase):
    answer: Dict[str, Any]
    bank_id: str

class QuestionResponse(QuestionBase):
    id: str
    bank_id: str
    created_at: datetime
    # answer is deliberately excluded from public response usually, but admin might need it.
    # We can create a separate QuestionAdminResponse if needed.

    model_config = ConfigDict(from_attributes=True)

class QuestionBankCreate(BaseModel):
    name: str
    description: Optional[str] = None

class QuestionBankResponse(QuestionBankCreate):
    id: str
    model_config = ConfigDict(from_attributes=True)
