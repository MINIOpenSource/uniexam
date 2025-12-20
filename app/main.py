from fastapi import FastAPI, Request, Depends, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.base import init_db, get_db
from app.db.models import AuditLog
from app.api.api import api_router
from app.services.rate_limiter import check_rate_limit
from app.core.security import get_password_hash
from app.db.models import User, UserRole
from sqlalchemy import select

# Lifespan event to init DB
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Create default admin if not exists
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        if not result.scalars().first():
            admin = User(
                username="admin",
                hashed_password=get_password_hash(settings.ADMIN_USER_DEFAULT_PASSWORD),
                role=UserRole.ADMIN
            )
            session.add(admin)
            await session.commit()

    yield

from app.db.base import AsyncSessionLocal # Need to import locally or move to base

app = FastAPI(
    title=settings.APP_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Rate Limiter Middleware (applied to all API routes via dependency injection in a middleware-like way or actually just middleware)
# Simple Middleware for Rate Limiting
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Skip rate limit for docs
    if request.url.path.startswith(settings.API_V1_STR):
        try:
            # We need a DB session here. Middleware is tricky with async generic depends.
            # We will manually create session.
            async with AsyncSessionLocal() as session:
                 # Check rate limit
                 from app.services.rate_limiter import RateLimiterService
                 limiter = RateLimiterService(session)
                 await limiter.check_rate_limit(f"ip:{request.client.host}")
        except Exception as e:
            if "Rate limit exceeded" in str(e) or (hasattr(e, "status_code") and e.status_code == 429):
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
            # Ignore other errors here or log them? For now proceed.
            pass

    response = await call_next(request)
    return response

# Audit Logging Middleware
@app.middleware("http")
async def audit_logging_middleware(request: Request, call_next):
    response = await call_next(request)

    # Only log state-changing methods or specific paths
    if request.method in ["POST", "PUT", "DELETE", "PATCH"] and request.url.path.startswith(settings.API_V1_STR):
        # We need to run this in background ideally, but for now inline async
        try:
             async with AsyncSessionLocal() as session:
                # Try to get user_id from state if Auth middleware put it there?
                # FastAPI doesn't easily share state from dependency to middleware unless we use custom Auth middleware.
                # For simplicity, we log IP and path.

                log = AuditLog(
                    action=f"{request.method} {request.url.path}",
                    ip_address=request.client.host,
                    details={"status_code": response.status_code}
                )
                session.add(log)
                await session.commit()
        except Exception:
            pass # Don't fail request on log fail

    return response

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Welcome to Online Exam System API"}
