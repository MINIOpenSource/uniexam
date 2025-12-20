from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, questions, papers, grading, audit

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(questions.router, prefix="/questions", tags=["questions"])
api_router.include_router(papers.router, prefix="/papers", tags=["papers"])
api_router.include_router(grading.router, prefix="/grading", tags=["grading"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
