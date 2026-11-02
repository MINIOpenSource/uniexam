import os
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app
from app.db import base as db_base
from app.db.base import Base
from app.core.config import settings
from app.db.seed import seed_question_banks


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    test_db_file = "./test_exam.db"
    test_db_url = f"sqlite+aiosqlite:///{test_db_file}"
    settings.SQLITE_DB_PATH = test_db_url

    test_engine = create_async_engine(
        test_db_url,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    db_base.engine = test_engine
    db_base.AsyncSessionLocal.configure(bind=test_engine)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
    if os.path.exists(test_db_file):
        os.remove(test_db_file)


@pytest_asyncio.fixture(scope="function")
async def client(db_engine):
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
                role=UserRole.ADMIN,
            )
            session.add(admin)
            await session.commit()

        await seed_question_banks(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_auth_flow(client):
    response = await client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "admin", "password": settings.ADMIN_USER_DEFAULT_PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]

    response = await client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "admin"


@pytest.mark.asyncio
async def test_create_user(client):
    login_res = await client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "admin", "password": settings.ADMIN_USER_DEFAULT_PASSWORD},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    user_data = {"username": "student1", "password": "password123", "role": "user"}
    response = await client.post(
        f"{settings.API_V1_STR}/users/", json=user_data, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["username"] == "student1"


@pytest.mark.asyncio
async def test_exam_flow(client):
    login_res = await client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "admin", "password": settings.ADMIN_USER_DEFAULT_PASSWORD},
    )
    admin_token = login_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create Question Bank
    bank_res = await client.post(
        f"{settings.API_V1_STR}/questions/banks",
        json={"name": "Math 101"},
        headers=admin_headers,
    )
    assert bank_res.status_code == 200
    bank_id = bank_res.json()["id"]

    # Create Question
    q_data = {
        "bank_id": bank_id,
        "type": "single_choice",
        "difficulty": 1,
        "content": {"body": "1+1=?", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}},
        "answer": {"correct_option_id": "B"},
    }
    await client.post(
        f"{settings.API_V1_STR}/questions/", json=q_data, headers=admin_headers
    )

    # Register student2 via self-registration endpoint
    reg_res = await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"username": "student2", "password": "password123"},
    )
    assert reg_res.status_code == 201

    # Login as student
    login_student = await client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "student2", "password": "password123"},
    )
    assert login_student.status_code == 200
    student_token = login_student.json()["access_token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # Verify non-admin cannot dump raw questions
    forbid_res = await client.get(
        f"{settings.API_V1_STR}/questions/", headers=student_headers
    )
    assert forbid_res.status_code == 403

    # Generate Paper
    paper_req = {
        "title": "Test Exam",
        "question_bank_id": bank_id,
        "difficulty": 1,
        "question_count": 1,
    }
    paper_res = await client.post(
        f"{settings.API_V1_STR}/papers/generate",
        json=paper_req,
        headers=student_headers,
    )
    assert paper_res.status_code == 200
    paper_json = paper_res.json()
    paper_id = paper_json["id"]
    issued_questions = paper_json["questions"]
    pq_id = issued_questions[0]["id"]
    options_map = issued_questions[0]["content"]["options"]

    # Every option key must be a valid UUID
    for k in options_map.keys():
        uuid.UUID(k)

    # Find the UUID corresponding to answer text "2"
    correct_uuid = next(k for k, v in options_map.items() if v == "2")

    # Submit Paper with issued questions and answer
    submission = {
        "questions": issued_questions,
        "paper_hash": paper_json["paper_hash"],
        "answers": {pq_id: {"selected_option_id": correct_uuid}},
    }
    submit_res = await client.post(
        f"{settings.API_V1_STR}/papers/{paper_id}/submit",
        json=submission,
        headers=student_headers,
    )
    assert submit_res.status_code == 200
    assert submit_res.json()["score"] == 1.0


@pytest.mark.asyncio
async def test_migrated_legacy_question_banks(client):
    login_student = await client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "student2", "password": "password123"},
    )
    student_token = login_student.json()["access_token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}

    banks_res = await client.get(
        f"{settings.API_V1_STR}/questions/banks", headers=student_headers
    )
    assert banks_res.status_code == 200
    bank_ids = {b["id"] for b in banks_res.json()}
    assert {"easy", "hybrid", "hard"}.issubset(bank_ids)

    # Generate a paper from migrated 'easy' bank without explicit difficulty
    paper_res = await client.post(
        f"{settings.API_V1_STR}/papers/generate",
        json={"title": "Legacy Easy Exam", "question_bank_id": "easy", "question_count": 5},
        headers=student_headers,
    )
    assert paper_res.status_code == 200
    assert len(paper_res.json()["questions"]) == 5


@pytest.mark.asyncio
async def test_uuid_options_different_per_issuance_and_hash_verification(client):
    login_student = await client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": "student2", "password": "password123"},
    )
    token = login_student.json()["access_token"]

    # 1. Start a paper via /get_exam
    exam_res = await client.get(
        f"/get_exam?token={token}&difficulty=easy&num_questions=5"
    )
    assert exam_res.status_code == 200
    exam_data_1 = exam_res.json()
    paper_id = exam_data_1["paper_id"]
    paper_1 = exam_data_1["paper"]
    hash_1 = exam_data_1["paper_hash"]
    assert len(paper_1) == 5

    # Verify all options are UUIDs
    for q in paper_1:
        assert len(q["choices"]) == 4
        for opt_id in q["choices"].keys():
            uuid.UUID(opt_id)

    # 2. Fetch the exact same paper again via /history_paper (simulating second device or refresh)
    hist_res = await client.get(f"/history_paper?token={token}&paper_id={paper_id}")
    assert hist_res.status_code == 200
    exam_data_2 = hist_res.json()
    paper_2 = exam_data_2["paper"]
    hash_2 = exam_data_2["paper_hash"]

    assert hash_1 != hash_2

    # Verify option UUIDs and option text order are strictly different for the same paper
    for q1, q2 in zip(paper_1, paper_2):
        assert q1["body"] == q2["body"]
        keys_1 = list(q1["choices"].keys())
        keys_2 = list(q2["choices"].keys())
        texts_1 = list(q1["choices"].values())
        texts_2 = list(q2["choices"].values())
        assert set(keys_1).isdisjoint(set(keys_2))  # Completely new UUIDs
        assert set(texts_1) == set(texts_2)  # Same underlying 4 choices
        assert texts_1 != texts_2  # Different shuffled order!

    # 3. Attempting to update progress WITHOUT submitting the issued paper fails
    bad_update_no_paper = await client.post(
        f"/update?token={token}",
        json={"paper_id": paper_id, "result": ["-1"] * 5},
    )
    assert bad_update_no_paper.status_code == 400

    # 4. Attempting to update progress with a tampered paper fails hash check
    tampered_paper = [dict(q, choices=dict(q["choices"])) for q in paper_1]
    first_key = next(iter(tampered_paper[0]["choices"]))
    tampered_paper[0]["choices"][first_key] = "Tampered Option Text"
    bad_update_tampered = await client.post(
        f"/update?token={token}",
        json={"paper_id": paper_id, "paper": tampered_paper, "result": [first_key, "-1", "-1", "-1", "-1"]},
    )
    assert bad_update_tampered.status_code == 400
    assert "INVALID_PAPER_HASH" in bad_update_tampered.text

    # 5. Valid update using Issuance 1 succeeds
    chosen_uuid_1 = next(iter(paper_1[0]["choices"].keys()))
    chosen_text = paper_1[0]["choices"][chosen_uuid_1]
    good_update = await client.post(
        f"/update?token={token}",
        json={
            "paper_id": paper_id,
            "paper": paper_1,
            "paper_hash": hash_1,
            "result": [chosen_uuid_1, "-1", "-1", "-1", "-1"],
        },
    )
    assert good_update.status_code == 200
    assert good_update.json()["status_code"] == "PROGRESS_SAVED"

    # 6. Fetching via /history_paper maps the saved answer to the new UUID of Issuance 3
    hist_res_3 = await client.get(f"/history_paper?token={token}&paper_id={paper_id}")
    assert hist_res_3.status_code == 200
    data_3 = hist_res_3.json()
    submitted_uuid_3 = data_3["submitted_answers_card"][0]
    assert submitted_uuid_3 != chosen_uuid_1
    assert data_3["paper"][0]["choices"][submitted_uuid_3] == chosen_text

    # 7. Finishing exam using Issuance 2 (which is also a valid retained hash on server) succeeds
    chosen_uuid_2 = next(k for k, v in paper_2[0]["choices"].items() if v == chosen_text)
    finish_res = await client.post(
        f"/finish?token={token}",
        json={
            "paper_id": paper_id,
            "paper": paper_2,
            "paper_hash": hash_2,
            "result": [chosen_uuid_2, "-1", "-1", "-1", "-1"],
        },
    )
    assert finish_res.status_code == 200
    assert finish_res.json()["status_code"] in ("PASSED", "FAILED")


def test_websocket_multi_device_realtime_sync(db_engine):
    with TestClient(app) as tc:
        login_res = tc.post(
            f"{settings.API_V1_STR}/auth/login",
            data={"username": "admin", "password": settings.ADMIN_USER_DEFAULT_PASSWORD},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        # Start an exam on Device A
        exam_res = tc.get(f"/get_exam?token={token}&difficulty=easy&num_questions=4")
        assert exam_res.status_code == 200
        exam_a = exam_res.json()
        paper_id = exam_a["paper_id"]
        paper_a = exam_a["paper"]
        hash_a = exam_a["paper_hash"]

        # Resume the same exam on Device B (gets different UUIDs and order)
        hist_res = tc.get(f"/history_paper?token={token}&paper_id={paper_id}")
        assert hist_res.status_code == 200
        exam_b = hist_res.json()
        paper_b = exam_b["paper"]

        with tc.websocket_connect(f"/ws?token={token}&device_id=dev-A&device_name=Laptop") as ws_a:
            conn_msg_a = ws_a.receive_json()
            assert conn_msg_a["type"] == "connected"

            with tc.websocket_connect(f"/ws?token={token}&device_id=dev-B&device_name=Tablet") as ws_b:
                # ws_a receives presence_update when dev-B connects
                pres_a = ws_a.receive_json()
                assert pres_a["type"] == "presence_update"
                assert pres_a["device_count"] == 2

                conn_msg_b = ws_b.receive_json()
                assert conn_msg_b["type"] == "connected"
                assert len(conn_msg_b["devices"]) == 2

                # Both devices join the paper
                ws_a.send_json({"type": "join_paper", "paper_id": paper_id, "current_question_index": 0})
                ws_b.send_json({"type": "join_paper", "paper_id": paper_id, "current_question_index": 0})

                # Device A selects an answer for question 0 and syncs via WebSocket
                opt_uuid_a = next(iter(paper_a[0]["choices"].keys()))
                opt_text = paper_a[0]["choices"][opt_uuid_a]

                ws_a.send_json({
                    "type": "sync_progress",
                    "paper_id": paper_id,
                    "paper": paper_a,
                    "paper_hash": hash_a,
                    "result": [opt_uuid_a, "-1", "-1", "-1"],
                    "current_question_index": 1,
                })

                # Drain messages on ws_b until we get progress_synced
                synced_msg = None
                for _ in range(10):
                    m = ws_b.receive_json()
                    if m.get("type") == "progress_synced":
                        synced_msg = m
                        break

                assert synced_msg is not None
                assert synced_msg["paper_id"] == paper_id
                assert synced_msg["selected_texts"][0] == opt_text
                assert synced_msg["finished_count"] == 1
                assert synced_msg["source_device_id"] == "dev-A"

                # Verify Device B can map that synced text to its own distinct UUID
                opt_uuid_b = next(k for k, v in paper_b[0]["choices"].items() if v == opt_text)
                assert opt_uuid_b != opt_uuid_a
