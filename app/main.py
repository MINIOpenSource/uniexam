from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.api import api_router
from app.api.v1.endpoints.legacy_compat import router as legacy_router
from app.api.v1.endpoints.ws import router as ws_router
from app.core.config import settings
from app.core.security import get_password_hash
from app.db.base import AsyncSessionLocal, init_db
from app.db.models import AuditLog, User, UserRole
from app.db.seed import seed_question_banks
from app.services.rate_limiter import RateLimiterService


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        if not result.scalars().first():
            admin = User(
                username="admin",
                hashed_password=get_password_hash(settings.ADMIN_USER_DEFAULT_PASSWORD),
                role=UserRole.ADMIN,
            )
            session.add(admin)
            await session.commit()

        await seed_question_banks(session)

    yield


app = FastAPI(
    title=settings.APP_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith(settings.API_V1_STR):
        client_host = request.client.host if request.client else "unknown"
        try:
            async with AsyncSessionLocal() as session:
                limiter = RateLimiterService(session)
                await limiter.check_rate_limit(f"ip:{client_host}")
        except HTTPException as e:
            if e.status_code == 429:
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        except Exception as e:
            if "Rate limit exceeded" in str(e):
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    response = await call_next(request)
    return response


@app.middleware("http")
async def audit_logging_middleware(request: Request, call_next):
    response = await call_next(request)

    if request.method in ["POST", "PUT", "DELETE", "PATCH"] and request.url.path.startswith(settings.API_V1_STR):
        client_host = request.client.host if request.client else "unknown"
        try:
            async with AsyncSessionLocal() as session:
                log = AuditLog(
                    action=f"{request.method} {request.url.path}",
                    ip_address=client_host,
                    details={"status_code": response.status_code},
                )
                session.add(log)
                await session.commit()
        except Exception:
            pass

    return response


app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(legacy_router)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {"message": "Welcome to Online Exam System API"}
