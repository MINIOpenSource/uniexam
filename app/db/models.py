import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import String, Boolean, Float, DateTime, ForeignKey, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.db.base import Base

# Enums
class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    MANAGER = "manager"

class QuestionType(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_IN_BLANK = "fill_in_blank"
    ESSAY = "essay"

class PaperStatus(str, Enum):
    PENDING = "pending"       # Created but not submitted
    SUBMITTED = "submitted"   # Submitted, waiting for grading
    GRADED = "graded"         # Grading complete (auto + manual)

# Models

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    role: Mapped[UserRole] = mapped_column(String, default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tokens: Mapped[List["Token"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    papers: Mapped[List["Paper"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship(back_populates="user")


class Token(Base):
    __tablename__ = "tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True) # Opaque token string
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="tokens")


class QuestionBank(Base):
    __tablename__ = "question_banks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String)

    questions: Mapped[List["Question"]] = relationship(back_populates="bank", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_id: Mapped[str] = mapped_column(ForeignKey("question_banks.id"))
    type: Mapped[QuestionType] = mapped_column(String)
    content: Mapped[dict] = mapped_column(JSON) # Stores body, options, etc.
    answer: Mapped[dict] = mapped_column(JSON)  # Stores correct answer(s) - Private
    difficulty: Mapped[int] = mapped_column(Integer, default=1) # 1-5 or similar
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bank: Mapped["QuestionBank"] = relationship(back_populates="questions")
    paper_questions: Mapped[List["PaperQuestion"]] = relationship(back_populates="question")


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String)
    status: Mapped[PaperStatus] = mapped_column(String, default=PaperStatus.PENDING)
    score: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="papers")
    paper_questions: Mapped[List["PaperQuestion"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    issued_hashes: Mapped[List["PaperHash"]] = relationship(back_populates="paper", cascade="all, delete-orphan")


class PaperQuestion(Base):
    __tablename__ = "paper_questions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id"))
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"))

    user_answer: Mapped[Optional[dict]] = mapped_column(JSON) # User's answer
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean)
    score_awarded: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, default=1.0) # Score value for this question
    manual_comment: Mapped[Optional[str]] = mapped_column(Text) # Teacher's feedback

    paper: Mapped["Paper"] = relationship(back_populates="paper_questions")
    question: Mapped["Question"] = relationship(back_populates="paper_questions")


class PaperHash(Base):
    __tablename__ = "paper_hashes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    paper_hash: Mapped[str] = mapped_column(String, index=True)
    option_map: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    paper: Mapped["Paper"] = relationship(back_populates="issued_hashes")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id")) # Can be null if system action or deleted user
    action: Mapped[str] = mapped_column(String)
    resource: Mapped[Optional[str]] = mapped_column(String)
    details: Mapped[Optional[dict]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="audit_logs")

class RateLimit(Base):
    __tablename__ = "rate_limits"

    key: Mapped[str] = mapped_column(String, primary_key=True) # e.g., "ip:127.0.0.1" or "user:uuid"
    count: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
