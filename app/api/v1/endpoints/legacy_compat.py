import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.db.base import get_db
from app.db.models import (
    Paper,
    PaperQuestion,
    PaperStatus,
    Question,
    QuestionBank,
    QuestionType,
    Token,
    User,
    UserRole,
)
from app.db.seed import DIFFICULTY_MAP, OPTION_LABELS
from app.services.auth import AuthService
from app.services.font_obfuscator import get_obfuscated_font_bytes
from app.services.grading import grading_service
from app.services.paper_hash import paper_issuance_service
from app.services.ws_manager import ws_manager
import random

router = APIRouter()

# In-memory profile metadata & settings for legacy v3 UI compatibility
_user_profiles_meta: Dict[str, Dict[str, Any]] = {}
_paper_meta: Dict[str, Dict[str, Any]] = {}
_runtime_settings: Dict[str, Any] = {
    "app_name": settings.APP_NAME,
    "token_expiry_hours": settings.ACCESS_TOKEN_EXPIRE_MINUTES // 60,
    "brandName": settings.APP_NAME,
}


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization") or request.headers.get("X-Access-Token")
    if auth_header:
        val = auth_header.strip()
        if val.lower().startswith("bearer "):
            val = val.split(" ", 1)[1].strip()
        if val:
            return val
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token is required in Authorization header",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _get_user_from_query_or_bearer(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token_str = _extract_bearer_token(request)
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_token(token_str)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is banned or inactive")
    return user


async def _get_admin_from_query_or_bearer(
    current_user: User = Depends(_get_user_from_query_or_bearer),
) -> User:
    if current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
    return current_user


def _build_user_profile(user: User) -> Dict[str, Any]:
    meta = _user_profiles_meta.get(user.username, {})
    tags: List[str] = ["USER"]
    if not user.is_active:
        tags = ["BANNED"]
    elif user.role == UserRole.ADMIN:
        tags = ["ADMIN", "MANAGER", "USER", "admin"]
    elif user.role == UserRole.MANAGER:
        tags = ["MANAGER", "USER"]

    extra_tags = meta.get("tags")
    if extra_tags:
        tags = list(dict.fromkeys(extra_tags + (["admin"] if "ADMIN" in extra_tags else [])))

    return {
        "uid": user.username,
        "nickname": meta.get("nickname") or user.username,
        "email": meta.get("email"),
        "qq": meta.get("qq"),
        "tags": tags,
    }


def _infer_difficulty(paper: Paper) -> str:
    meta = _paper_meta.get(paper.id, {})
    if meta.get("difficulty"):
        return meta["difficulty"]
    if paper.title and ":" in paper.title:
        prefix = paper.title.split(":", 1)[0].strip().lower()
        if prefix in ("easy", "hybrid", "hard"):
            return prefix
    if paper.paper_questions:
        first_q = paper.paper_questions[0].question
        if first_q and first_q.bank_id in ("easy", "hybrid", "hard"):
            return first_q.bank_id
    return "easy"


def _compute_pass_status(paper: Paper) -> Optional[str]:
    if paper.status == PaperStatus.PENDING:
        return None
    meta = _paper_meta.get(paper.id, {})
    if meta.get("pass_status"):
        return meta["pass_status"]
    total = paper.total_score or len(paper.paper_questions) or 1.0
    score = paper.score or 0.0
    pct = (score / total) * 100.0 if total > 0 else 0.0
    return "PASSED" if pct >= 60.0 else "FAILED"


# --- Schemas ---

class LegacySigninPayload(BaseModel):
    uid: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    nickname: Optional[str] = None
    email: Optional[str] = None
    qq: Optional[str] = None


class LegacyProfileUpdatePayload(BaseModel):
    nickname: Optional[str] = None
    email: Optional[str] = None
    qq: Optional[str] = None


class LegacyPasswordUpdatePayload(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=128)


class LegacyPaperSubmissionPayload(BaseModel):
    paper_id: str
    paper: Optional[List[Dict[str, Any]]] = None
    result: List[Optional[str]]
    paper_hash: Optional[str] = None
    current_question_index: Optional[int] = None
    device_id: Optional[str] = None


class LegacyAdminUserUpdatePayload(BaseModel):
    nickname: Optional[str] = None
    email: Optional[str] = None
    qq: Optional[str] = None
    tags: Optional[List[str]] = None
    new_password: Optional[str] = None


# --- Auth Endpoints ---

@router.post("/auth/signin", status_code=status.HTTP_201_CREATED)
async def legacy_signin(payload: LegacySigninPayload, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == payload.uid))
    if result.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered")

    user = User(
        username=payload.uid,
        hashed_password=get_password_hash(payload.password),
        role=UserRole.USER,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    _user_profiles_meta[user.username] = {
        "nickname": payload.nickname,
        "email": payload.email,
        "qq": payload.qq,
    }

    auth_service = AuthService(db)
    token = await auth_service.create_user_token(user.id)
    return {
        "access_token": token.token,
        "token_type": "bearer",
        "uid": user.username,
        "expires_at": token.expires_at,
    }


@router.post("/auth/login")
async def legacy_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    auth_service = AuthService(db)
    user = await auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    token = await auth_service.create_user_token(user.id)
    return {
        "access_token": token.token,
        "token_type": "bearer",
        "uid": user.username,
        "expires_at": token.expires_at,
    }


@router.get("/auth/login")
async def legacy_refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = _extract_bearer_token(request)
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_token(token)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    return {
        "access_token": token,
        "token_type": "bearer",
        "uid": user.username,
    }


# --- User Profile Endpoints ---

@router.get("/users/me")
async def legacy_get_me(current_user: User = Depends(_get_user_from_query_or_bearer)):
    return _build_user_profile(current_user)


@router.put("/users/me")
async def legacy_update_me(
    payload: LegacyProfileUpdatePayload,
    current_user: User = Depends(_get_user_from_query_or_bearer),
):
    meta = _user_profiles_meta.setdefault(current_user.username, {})
    if payload.nickname is not None:
        meta["nickname"] = payload.nickname
    if payload.email is not None:
        meta["email"] = payload.email
    if payload.qq is not None:
        meta["qq"] = payload.qq
    return _build_user_profile(current_user)


@router.put("/users/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def legacy_update_password(
    payload: LegacyPasswordUpdatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_user_from_query_or_bearer),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect current password")
    current_user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Public Endpoints ---

@router.get("/difficulties")
async def legacy_get_difficulties(db: AsyncSession = Depends(get_db)):
    banks = (await db.execute(select(QuestionBank))).scalars().all()
    defaults = {"easy": 30, "hybrid": 50, "hard": 20}
    items = []
    for b in banks:
        q_count = (
            await db.execute(select(func.count()).select_from(Question).where(Question.bank_id == b.id))
        ).scalar() or 0
        items.append({
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "default_questions": defaults.get(b.id, 20),
            "total_questions": q_count,
        })
    return items


@router.get("/users/directory")
async def legacy_users_directory(db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(User).where(User.is_active == True))).scalars().all()
    return [
        {
            "uid": u.username,
            "nickname": _user_profiles_meta.get(u.username, {}).get("nickname") or u.username,
            "tags": _build_user_profile(u)["tags"],
        }
        for u in users
    ]


# --- Exam Flow Endpoints ---

@router.get("/exam/font/{font_id}")
@router.get("/api/exam/font/{font_id}")
async def legacy_get_obfuscated_font(font_id: str):
    ttf_bytes = get_obfuscated_font_bytes(font_id)
    if not ttf_bytes:
        raise HTTPException(status_code=404, detail="Font resource expired or not found")
    return Response(
        content=ttf_bytes,
        media_type="font/ttf",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/get_exam")
async def legacy_get_exam(
    request: Request,
    difficulty: str = Query(default="easy"),
    num_questions: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_user_from_query_or_bearer),
):
    defaults = {"easy": 30, "hybrid": 50, "hard": 20}
    count = num_questions if (num_questions and num_questions > 0) else defaults.get(difficulty, 20)

    stmt = select(Question).where(Question.bank_id == difficulty)
    available = (await db.execute(stmt)).scalars().all()
    if not available:
        raise HTTPException(status_code=400, detail=f"Question bank '{difficulty}' not found or empty")

    count = min(count, len(available))
    selected = random.sample(available, count)

    paper = Paper(
        user_id=current_user.id,
        title=f"{difficulty}:{current_user.username}",
        status=PaperStatus.PENDING,
        total_score=float(len(selected)),
    )
    db.add(paper)
    await db.flush()

    for q in selected:
        pq = PaperQuestion(
            paper_id=paper.id,
            question_id=q.id,
            max_score=1.0,
        )
        db.add(pq)

    await db.flush()

    stmt_full = (
        select(Paper)
        .options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question))
        .where(Paper.id == paper.id)
    )
    paper_full = (await db.execute(stmt_full)).scalars().first()
    client_questions, _, paper_hash = await paper_issuance_service.issue_legacy_paper(paper_full, db=db)

    await db.commit()

    client_ip = request.client.host if request.client else "127.0.0.1"
    now_iso = datetime.now(timezone.utc).isoformat()
    _paper_meta[paper.id] = {
        "difficulty": difficulty,
        "creation_ip": client_ip,
        "last_update_time_utc": now_iso,
        "last_update_ip": client_ip,
    }

    await ws_manager.broadcast_to_user(
        current_user.username,
        {
            "type": "exam_created",
            "paper_id": paper.id,
            "difficulty": difficulty,
            "creation_time_utc": now_iso,
        },
    )
    await ws_manager.broadcast_to_admins(
        {
            "type": "admin_paper_updated",
            "paper_id": paper.id,
            "action": "created",
        }
    )
    await ws_manager.record_live_event(
        category="exam",
        severity="info",
        username=current_user.username,
        device_id="http",
        device_name="Web Client",
        ip_address=client_ip,
        message=f"生成新试卷 ({paper.id[:8]}... · 难度: {difficulty} · 共 {len(client_questions)} 题)",
        paper_id=paper.id,
    )

    return {
        "paper_id": paper.id,
        "difficulty": difficulty,
        "paper": client_questions,
        "paper_hash": paper_hash,
    }


@router.post("/update")
async def legacy_update_exam(
    request: Request,
    payload: LegacyPaperSubmissionPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_user_from_query_or_bearer),
):
    stmt = (
        select(Paper)
        .options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question))
        .where(Paper.id == payload.paper_id)
    )
    paper = (await db.execute(stmt)).scalars().first()
    if not paper:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if paper.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your paper")
    if paper.status != PaperStatus.PENDING:
        raise HTTPException(status_code=400, detail="ALREADY_GRADED")

    try:
        resolved_answers, selected_texts = await paper_issuance_service.verify_and_resolve_legacy_submission(
            paper=paper,
            submitted_paper=payload.paper,
            submitted_result=payload.result,
            submitted_hash=payload.paper_hash,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    for idx, pq in enumerate(paper.paper_questions):
        pq.user_answer = resolved_answers[idx]

    await db.commit()

    now_iso = datetime.now(timezone.utc).isoformat()
    meta = _paper_meta.setdefault(paper.id, {})
    meta["last_update_time_utc"] = now_iso
    meta["last_update_ip"] = request.client.host if request.client else "127.0.0.1"

    finished_count = sum(1 for a in resolved_answers if a is not None)
    selected_canon_ids = [
        a.get("selected_option_id") if isinstance(a, dict) else None
        for a in resolved_answers
    ]

    await ws_manager.broadcast_to_user(
        current_user.username,
        {
            "type": "progress_synced",
            "paper_id": paper.id,
            "selected_texts": selected_texts,
            "selected_canon_ids": selected_canon_ids,
            "current_question_index": payload.current_question_index,
            "finished_count": finished_count,
            "total_count": len(paper.paper_questions),
            "source_device_id": payload.device_id,
            "last_update_time_utc": now_iso,
        },
        exclude_device_id=payload.device_id,
    )
    await ws_manager.broadcast_to_admins(
        {
            "type": "admin_paper_updated",
            "paper_id": paper.id,
            "action": "progress",
            "finished_count": finished_count,
        }
    )

    return {
        "status_code": "PROGRESS_SAVED",
        "message": "Progress saved",
        "paper_id": paper.id,
        "last_update_time_utc": now_iso,
    }


@router.post("/finish")
async def legacy_finish_exam(
    request: Request,
    payload: LegacyPaperSubmissionPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_user_from_query_or_bearer),
):
    stmt = (
        select(Paper)
        .options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question))
        .where(Paper.id == payload.paper_id)
    )
    paper = (await db.execute(stmt)).scalars().first()
    if not paper:
        return {"status_code": "NOT_FOUND", "message": "Paper not found"}
    if paper.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your paper")
    if paper.status != PaperStatus.PENDING:
        return {"status_code": "ALREADY_GRADED", "message": "Paper already submitted"}

    try:
        resolved_answers, selected_texts = await paper_issuance_service.verify_and_resolve_legacy_submission(
            paper=paper,
            submitted_paper=payload.paper,
            submitted_result=payload.result,
            submitted_hash=payload.paper_hash,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_awarded = 0.0
    for idx, pq in enumerate(paper.paper_questions):
        ans_dict = resolved_answers[idx]
        if ans_dict is not None:
            pq.user_answer = ans_dict
            mult = grading_service.grade_question(pq.question, ans_dict)
            pq.score_awarded = mult * pq.max_score
            pq.is_correct = (mult == 1.0)
            total_awarded += pq.score_awarded
        else:
            pq.user_answer = None
            pq.score_awarded = 0.0
            pq.is_correct = False

    paper.score = total_awarded
    paper.status = PaperStatus.GRADED
    paper.submitted_at = datetime.now(timezone.utc)
    await db.commit()

    total_possible = paper.total_score or len(paper.paper_questions) or 1.0
    pct = round((total_awarded / total_possible) * 100.0, 2) if total_possible > 0 else 0.0
    passed = pct >= 60.0
    pass_status = "PASSED" if passed else "FAILED"
    passcode = secrets.token_hex(4).upper() if passed else None

    meta = _paper_meta.setdefault(paper.id, {})
    meta["pass_status"] = pass_status
    meta["passcode"] = passcode
    meta["submission_ip"] = request.client.host if request.client else "127.0.0.1"
    meta["last_update_time_utc"] = paper.submitted_at.isoformat()

    result_payload = {
        "status_code": pass_status,
        "message": "Exam graded successfully",
        "passcode": passcode,
        "score": int(round(pct)),
        "score_percentage": pct,
        "pending_manual_grading_count": 0,
    }

    await ws_manager.broadcast_to_user(
        current_user.username,
        {
            "type": "exam_finished",
            "paper_id": paper.id,
            "source_device_id": payload.device_id,
            "submission_time_utc": paper.submitted_at.isoformat(),
            **result_payload,
        },
        exclude_device_id=payload.device_id,
    )
    await ws_manager.broadcast_to_admins(
        {
            "type": "admin_paper_updated",
            "paper_id": paper.id,
            "action": "finished",
            "pass_status": pass_status,
            "score": int(round(pct)),
        }
    )

    return result_payload


# --- History Endpoints ---

@router.get("/history")
async def legacy_user_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_user_from_query_or_bearer),
):
    stmt = (
        select(Paper)
        .options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question))
        .where(Paper.user_id == current_user.id)
        .order_by(Paper.created_at.desc())
    )
    papers = (await db.execute(stmt)).scalars().all()
    items = []
    for p in papers:
        total = p.total_score or len(p.paper_questions) or 1.0
        pct = round(((p.score or 0.0) / total) * 100.0, 2) if p.status != PaperStatus.PENDING and total > 0 else None
        items.append({
            "paper_id": p.id,
            "difficulty": _infer_difficulty(p),
            "score": int(round(pct)) if pct is not None else None,
            "score_percentage": pct,
            "pass_status": _compute_pass_status(p),
            "submission_time_utc": p.submitted_at.isoformat() if p.submitted_at else None,
        })
    return items


@router.get("/history_paper")
async def legacy_history_paper_detail(
    paper_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_user_from_query_or_bearer),
):
    stmt = (
        select(Paper)
        .options(selectinload(Paper.paper_questions).selectinload(PaperQuestion.question))
        .where(Paper.id == paper_id)
    )
    paper = (await db.execute(stmt)).scalars().first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.user_id != current_user.id and current_user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="Not your paper")

    client_questions, submitted_card, paper_hash = await paper_issuance_service.issue_legacy_paper(paper, db=db)
    await db.commit()

    questions_view = []
    for idx, pq in enumerate(paper.paper_questions):
        cq = client_questions[idx]
        questions_view.append({
            "body": cq["body"],
            "question_type": cq["question_type"],
            "choices": cq["choices"],
            "obfuscated_font": cq.get("obfuscated_font"),
            "submitted_answer": submitted_card[idx],
            "student_subjective_answer": None,
            "standard_answer_text": None,
            "manual_score": pq.score_awarded,
            "teacher_comment": pq.manual_comment,
        })

    total = paper.total_score or len(paper.paper_questions) or 1.0
    pct = round(((paper.score or 0.0) / total) * 100.0, 2) if paper.status != PaperStatus.PENDING and total > 0 else None
    meta = _paper_meta.get(paper.id, {})

    return {
        "paper_id": paper.id,
        "difficulty": _infer_difficulty(paper),
        "user_uid": current_user.username,
        "paper_questions": questions_view,
        "paper": client_questions,
        "paper_hash": paper_hash,
        "score": int(round(pct)) if pct is not None else None,
        "score_percentage": pct,
        "submitted_answers_card": submitted_card,
        "pass_status": _compute_pass_status(paper),
        "passcode": meta.get("passcode"),
        "submission_time_utc": paper.submitted_at.isoformat() if paper.submitted_at else None,
        "subjective_questions_count": 0,
        "graded_subjective_questions_count": 0,
        "pending_manual_grading_count": 0,
    }


# --- Admin Endpoints ---

@router.get("/admin/settings")
async def legacy_admin_get_settings(admin: User = Depends(_get_admin_from_query_or_bearer)):
    return _runtime_settings


@router.post("/admin/settings")
async def legacy_admin_update_settings(
    payload: Dict[str, Any],
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    if "app_name" in payload and payload["app_name"]:
        _runtime_settings["app_name"] = payload["app_name"]
        _runtime_settings["brandName"] = payload["app_name"]
    if "brandName" in payload and payload["brandName"]:
        _runtime_settings["brandName"] = payload["brandName"]
    if "token_expiry_hours" in payload and payload["token_expiry_hours"]:
        _runtime_settings["token_expiry_hours"] = payload["token_expiry_hours"]
    return _runtime_settings


@router.get("/admin/users")
async def legacy_admin_list_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    users = (await db.execute(select(User).offset(skip).limit(limit))).scalars().all()
    return [_build_user_profile(u) for u in users]


@router.get("/admin/users/{user_uid}")
async def legacy_admin_user_detail(
    user_uid: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    user = (await db.execute(select(User).where(User.username == user_uid))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _build_user_profile(user)


@router.put("/admin/users/{user_uid}")
async def legacy_admin_user_update(
    user_uid: str,
    payload: LegacyAdminUserUpdatePayload,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    user = (await db.execute(select(User).where(User.username == user_uid))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    meta = _user_profiles_meta.setdefault(user.username, {})
    if payload.nickname is not None:
        meta["nickname"] = payload.nickname
    if payload.email is not None:
        meta["email"] = payload.email
    if payload.qq is not None:
        meta["qq"] = payload.qq
    if payload.tags is not None:
        meta["tags"] = payload.tags
        upper_tags = {t.upper() for t in payload.tags}
        if "BANNED" in upper_tags:
            user.is_active = False
            await ws_manager.disconnect_all_for_user(user.username, reason="Account has been banned")
        else:
            user.is_active = True
            if "ADMIN" in upper_tags:
                user.role = UserRole.ADMIN
            elif "MANAGER" in upper_tags:
                user.role = UserRole.MANAGER
            else:
                user.role = UserRole.USER

    if payload.new_password:
        user.hashed_password = get_password_hash(payload.new_password)

    await db.commit()
    await db.refresh(user)
    return _build_user_profile(user)


@router.get("/admin/papers")
async def legacy_admin_list_papers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    stmt = (
        select(Paper)
        .options(
            selectinload(Paper.user),
            selectinload(Paper.paper_questions).selectinload(PaperQuestion.question),
        )
        .order_by(Paper.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    papers = (await db.execute(stmt)).scalars().all()
    result = []
    for p in papers:
        meta = _paper_meta.get(p.id, {})
        total_q = len(p.paper_questions)
        finished_q = sum(1 for pq in p.paper_questions if pq.user_answer)
        correct_q = sum(1 for pq in p.paper_questions if pq.is_correct)
        total = p.total_score or total_q or 1.0
        pct = round(((p.score or 0.0) / total) * 100.0, 2) if p.status != PaperStatus.PENDING and total > 0 else None

        result.append({
            "paper_id": p.id,
            "user_uid": p.user.username if p.user else None,
            "creation_time_utc": p.created_at.isoformat() if p.created_at else datetime.now(timezone.utc).isoformat(),
            "creation_ip": meta.get("creation_ip", "127.0.0.1"),
            "difficulty": _infer_difficulty(p),
            "count": total_q,
            "finished_count": finished_q,
            "correct_count": correct_q,
            "score": int(round(pct)) if pct is not None else None,
            "score_percentage": pct,
            "submission_time_utc": p.submitted_at.isoformat() if p.submitted_at else None,
            "submission_ip": meta.get("submission_ip"),
            "pass_status": _compute_pass_status(p),
            "passcode": meta.get("passcode"),
            "last_update_time_utc": meta.get("last_update_time_utc") or (p.submitted_at.isoformat() if p.submitted_at else p.created_at.isoformat()),
            "last_update_ip": meta.get("last_update_ip", "127.0.0.1"),
            "subjective_questions_count": 0,
            "graded_subjective_questions_count": 0,
            "pending_manual_grading_count": 0,
        })
    return result


@router.get("/admin/papers/{paper_id}")
async def legacy_admin_paper_detail(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    stmt = (
        select(Paper)
        .options(
            selectinload(Paper.user),
            selectinload(Paper.paper_questions).selectinload(PaperQuestion.question),
        )
        .where(Paper.id == paper_id)
    )
    p = (await db.execute(stmt)).scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")

    meta = _paper_meta.get(p.id, {})
    detailed_questions = []
    submitted_card = []

    for pq in p.paper_questions:
        q = pq.question
        options = q.content.get("options", {})
        corr_id = q.answer.get("correct_option_id")
        corr_ids = set(q.answer.get("correct_option_ids", []))
        if corr_id:
            corr_ids.add(corr_id)

        correct_map = {k: v for k, v in options.items() if k in corr_ids}
        incorrect_map = {k: v for k, v in options.items() if k not in corr_ids}

        ans_id = pq.user_answer.get("selected_option_id") if isinstance(pq.user_answer, dict) else None
        submitted_card.append(ans_id if ans_id else "-1")

        detailed_questions.append({
            "internal_question_id": pq.id,
            "body": q.content.get("body", ""),
            "question_type": q.type.value if hasattr(q.type, "value") else str(q.type),
            "correct_choices_map": correct_map,
            "incorrect_choices_map": incorrect_map,
            "standard_answer_text": q.answer.get("reference"),
            "student_subjective_answer": None,
            "manual_score": pq.score_awarded,
            "teacher_comment": pq.manual_comment,
        })

    total = p.total_score or len(p.paper_questions) or 1.0
    pct = round(((p.score or 0.0) / total) * 100.0, 2) if p.status != PaperStatus.PENDING and total > 0 else None

    return {
        "paper_id": p.id,
        "user_uid": p.user.username if p.user else None,
        "creation_time_utc": p.created_at.isoformat() if p.created_at else datetime.now(timezone.utc).isoformat(),
        "creation_ip": meta.get("creation_ip", "127.0.0.1"),
        "difficulty": _infer_difficulty(p),
        "paper_questions": detailed_questions,
        "submitted_answers_card": submitted_card,
        "score": int(round(pct)) if pct is not None else None,
        "total_score": p.score,
        "score_percentage": pct,
        "submission_time_utc": p.submitted_at.isoformat() if p.submitted_at else None,
        "submission_ip": meta.get("submission_ip"),
        "pass_status": _compute_pass_status(p),
        "passcode": meta.get("passcode"),
        "last_update_time_utc": meta.get("last_update_time_utc") or (p.submitted_at.isoformat() if p.submitted_at else p.created_at.isoformat()),
        "last_update_ip": meta.get("last_update_ip", "127.0.0.1"),
        "subjective_questions_count": 0,
        "graded_subjective_questions_count": 0,
        "pending_manual_grading_count": 0,
    }


@router.delete("/admin/papers/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def legacy_admin_delete_paper(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    stmt = select(Paper).where(Paper.id == paper_id)
    p = (await db.execute(stmt)).scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    await db.delete(p)
    await db.commit()
    _paper_meta.pop(paper_id, None)
    paper_issuance_service.clear_paper_hashes(paper_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/question-banks")
async def legacy_admin_question_banks(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    return await legacy_get_difficulties(db)


@router.get("/admin/question-banks/{difficulty_id}/content")
async def legacy_admin_question_bank_content(
    difficulty_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    bank = (await db.execute(select(QuestionBank).where(QuestionBank.id == difficulty_id))).scalars().first()
    if not bank:
        raise HTTPException(status_code=404, detail="Question bank not found")

    questions = (
        await db.execute(select(Question).where(Question.bank_id == difficulty_id).order_by(Question.created_at.asc()))
    ).scalars().all()

    q_models = []
    for q in questions:
        options = q.content.get("options", {})
        corr_id = q.answer.get("correct_option_id")
        corr_ids = set(q.answer.get("correct_option_ids", []))
        if corr_id:
            corr_ids.add(corr_id)

        correct_choices = [v for k, v in options.items() if k in corr_ids]
        incorrect_choices = [v for k, v in options.items() if k not in corr_ids]

        q_models.append({
            "body": q.content.get("body", ""),
            "question_type": q.type.value if hasattr(q.type, "value") else str(q.type),
            "correct_choices": correct_choices,
            "incorrect_choices": incorrect_choices,
            "num_correct_to_select": len(correct_choices) or 1,
        })

    defaults = {"easy": 30, "hybrid": 50, "hard": 20}
    return {
        "metadata": {
            "id": bank.id,
            "name": bank.name,
            "description": bank.description,
            "default_questions": defaults.get(bank.id, 20),
            "total_questions": len(q_models),
        },
        "questions": q_models,
    }


@router.post("/admin/question-banks/{difficulty_id}/questions", status_code=status.HTTP_201_CREATED)
async def legacy_admin_add_question(
    difficulty_id: str,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    bank = (await db.execute(select(QuestionBank).where(QuestionBank.id == difficulty_id))).scalars().first()
    if not bank:
        raise HTTPException(status_code=404, detail="Question bank not found")

    body = (payload.get("body") or "").strip()
    correct_choices = payload.get("correct_choices") or []
    incorrect_choices = payload.get("incorrect_choices") or []
    if not body or not correct_choices or not incorrect_choices:
        raise HTTPException(status_code=400, detail="Invalid question payload")

    combined = [(correct_choices[0], True)] + [(d, False) for d in incorrect_choices[:3]]
    random.shuffle(combined)
    options = {}
    correct_option_id = "A"
    for idx, (text, is_corr) in enumerate(combined):
        label = OPTION_LABELS[idx]
        options[label] = text
        if is_corr:
            correct_option_id = label

    q = Question(
        bank_id=difficulty_id,
        type=QuestionType.SINGLE_CHOICE,
        content={"body": body, "options": options},
        answer={"correct_option_id": correct_option_id},
        difficulty=DIFFICULTY_MAP.get(difficulty_id, 1),
    )
    db.add(q)
    await db.commit()
    return payload


@router.delete("/admin/question-banks/{difficulty_id}/questions", status_code=status.HTTP_204_NO_CONTENT)
async def legacy_admin_delete_question(
    difficulty_id: str,
    index: int = Query(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    questions = (
        await db.execute(select(Question).where(Question.bank_id == difficulty_id).order_by(Question.created_at.asc()))
    ).scalars().all()
    if index < 0 or index >= len(questions):
        raise HTTPException(status_code=404, detail="Question index out of range")
    await db.delete(questions[index])
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/grading/pending-papers")
async def legacy_admin_pending_papers(
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    return []


@router.get("/admin/tokens")
async def legacy_admin_list_tokens(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    tokens = (await db.execute(select(Token).options(selectinload(Token.user)))).scalars().all()
    return [
        {
            "token": t.token,
            "user_uid": t.user.username if t.user else t.user_id,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tokens
    ]


@router.delete("/admin/tokens/user/{user_uid}")
async def legacy_admin_revoke_user_tokens(
    user_uid: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    user = (await db.execute(select(User).where(User.username == user_uid))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    res = await db.execute(delete(Token).where(Token.user_id == user.id))
    await db.commit()
    await ws_manager.disconnect_all_for_user(user_uid, reason="All tokens revoked by administrator")
    return {"message": "Tokens revoked", "invalidated_count": res.rowcount or 0}


@router.delete("/admin/tokens/{token_string}", status_code=status.HTTP_204_NO_CONTENT)
async def legacy_admin_revoke_single_token(
    token_string: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_get_admin_from_query_or_bearer),
):
    await db.execute(delete(Token).where(Token.token == token_string))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
