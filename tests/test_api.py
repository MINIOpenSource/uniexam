import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.base import init_db, engine, Base
from app.core.config import settings
import os

# Test Fixtures

@pytest_asyncio.fixture(scope="session")
async def db_engine():
    # Setup
    test_db_path = "sqlite+aiosqlite:///./test_exam.db"
    settings.SQLITE_DB_PATH = test_db_path

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Teardown
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    if os.path.exists("./test_exam.db"):
        os.remove("./test_exam.db")

@pytest_asyncio.fixture(scope="function")
async def client(db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_auth_flow(client):
    # 1. Login with default admin (created by lifespan)
    # Note: lifespan is not automatically triggered by ASGITransport unless we use TestClient with context manager or similar.
    # However, since we are using shared DB engine, the DB init might have happened in `db_engine` fixture BUT the admin creation is in `lifespan`.
    # `db_engine` fixture just creates tables. `lifespan` creates admin.
    # We need to manually trigger admin creation or use a fixture for it.

    # Let's manually ensure admin exists
    from app.db.base import AsyncSessionLocal
    from app.db.models import User, UserRole
    from app.core.security import get_password_hash
    from sqlalchemy import select

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

    response = await client.post(f"{settings.API_V1_STR}/auth/login", data={"username": "admin", "password": settings.ADMIN_USER_DEFAULT_PASSWORD})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]

    # 2. Get Me
    response = await client.get(f"{settings.API_V1_STR}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "admin"

@pytest.mark.asyncio
async def test_create_user(client):
    # Ensure admin exists (idempotent)
    from app.db.base import AsyncSessionLocal
    from app.db.models import User, UserRole
    from app.core.security import get_password_hash
    from sqlalchemy import select

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

    # Login as admin
    login_res = await client.post(f"{settings.API_V1_STR}/auth/login", data={"username": "admin", "password": settings.ADMIN_USER_DEFAULT_PASSWORD})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create new user
    user_data = {"username": "student1", "password": "password123", "role": "user"}
    response = await client.post(f"{settings.API_V1_STR}/users/", json=user_data, headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "student1"

@pytest.mark.asyncio
async def test_exam_flow(client):
    # Ensure admin exists
    from app.db.base import AsyncSessionLocal
    from app.db.models import User, UserRole
    from app.core.security import get_password_hash
    from sqlalchemy import select

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

    # Login as admin
    login_res = await client.post(f"{settings.API_V1_STR}/auth/login", data={"username": "admin", "password": settings.ADMIN_USER_DEFAULT_PASSWORD})
    admin_token = login_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create Question Bank
    bank_res = await client.post(f"{settings.API_V1_STR}/questions/banks", json={"name": "Math 101"}, headers=admin_headers)
    assert bank_res.status_code == 200
    bank_id = bank_res.json()["id"]

    # Create Question
    q_data = {
        "bank_id": bank_id,
        "type": "single_choice",
        "difficulty": 1,
        "content": {"body": "1+1=?", "options": {"A": "1", "B": "2"}},
        "answer": {"correct_option_id": "B"}
    }
    await client.post(f"{settings.API_V1_STR}/questions/", json=q_data, headers=admin_headers)

    # Create student2 if not exists
    await client.post(f"{settings.API_V1_STR}/users/", json={"username": "student2", "password": "password123"}, headers=admin_headers)

    # Login as student
    login_student = await client.post(f"{settings.API_V1_STR}/auth/login", data={"username": "student2", "password": "password123"})
    assert login_student.status_code == 200
    student_token = login_student.json()["access_token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # Generate Paper
    paper_req = {"title": "Test Exam", "question_bank_id": bank_id, "question_count": 1}
    paper_res = await client.post(f"{settings.API_V1_STR}/papers/generate", json=paper_req, headers=student_headers)
    assert paper_res.status_code == 200
    paper_id = paper_res.json()["id"]
    pq_id = paper_res.json()["questions"][0]["id"]

    # Submit Paper
    submission = {"answers": {pq_id: {"selected_option_id": "B"}}}
    submit_res = await client.post(f"{settings.API_V1_STR}/papers/{paper_id}/submit", json=submission, headers=student_headers)
    assert submit_res.status_code == 200
    assert submit_res.json()["score"] == 1.0 # Assuming 1.0 per question
