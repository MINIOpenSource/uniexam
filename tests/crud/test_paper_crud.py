# -*- coding: utf-8 -*-
"""
app.crud.paper.PaperCRUD 类的单元测试。
(Unit tests for the app.crud.paper.PaperCRUD class.)
"""

import uuid
from datetime import datetime  # ADDED: F821: datetime used for timestamps
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request as FastAPIRequest  # To mock request object

from app.core.interfaces import IDataStorageRepository, IQuestionBankCRUD
from app.crud.paper import PAPER_ENTITY_TYPE, PaperCRUD
from app.models.enums import DifficultyLevel, QuestionTypeEnum
from app.models.paper_models import (
    PaperInDB,
    PaperQuestionInternalDetail,
    PaperStatusEnum,
)
from app.models.qb_models import QuestionModel

# 全局测试数据 (Global test data for this file)
TEST_USER_UID = "paper_test_user_01"  # ADDED: F821: Used in tests

# region Fixtures (测试固件)


@pytest.fixture
def mock_repo(mocker) -> AsyncMock:
    """提供一个被模拟的 IDataStorageRepository 实例的Fixture。"""
    repo = AsyncMock(spec=IDataStorageRepository)
    repo.get_by_id = AsyncMock()
    repo.get_all = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.query = AsyncMock()
    repo.init_storage_if_needed = AsyncMock()
    return repo


@pytest.fixture
def mock_qb_crud(mocker) -> AsyncMock:
    """提供一个被模拟的 IQuestionBankCRUD 实例的Fixture。"""
    qb_crud = AsyncMock(spec=IQuestionBankCRUD)
    qb_crud.get_questions_for_paper = AsyncMock()
    return qb_crud


@pytest.fixture
def paper_crud_instance(mock_repo: AsyncMock, mock_qb_crud: AsyncMock) -> PaperCRUD:
    """提供一个 PaperCRUD 实例，并注入模拟的仓库和题库CRUD。"""
    return PaperCRUD(repository=mock_repo, qb_crud=mock_qb_crud)


@pytest.fixture
def mock_request() -> MagicMock:
    """提供一个 FastAPI Request 对象的简单模拟。"""
    req = MagicMock(spec=FastAPIRequest)
    req.app = MagicMock()
    req.app.state = MagicMock()
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.client.port = 8000
    req.headers = MagicMock()
    req.headers.get = MagicMock(return_value="test-user-agent")
    return req


# endregion

# region 基础测试 (Basic Tests)


@pytest.mark.asyncio
async def test_initialize_storage(paper_crud_instance: PaperCRUD, mock_repo: AsyncMock):
    """测试 initialize_storage 方法是否正确调用仓库的初始化。"""
    await paper_crud_instance.initialize_storage()
    mock_repo.init_storage_if_needed.assert_called_once_with(PAPER_ENTITY_TYPE, [])


# endregion

# region create_new_paper 测试 (create_new_paper Tests)


def _create_mock_question(
    q_id: str,
    q_type: QuestionTypeEnum = QuestionTypeEnum.SINGLE_CHOICE,
    body: str = "题目内容",
) -> QuestionModel:
    """辅助函数：创建模拟题目模型。"""
    return QuestionModel(
        id=q_id,
        body=body,
        question_type=q_type,
        correct_choices=(
            ["正确答案A"] if q_type == QuestionTypeEnum.SINGLE_CHOICE else None
        ),
        incorrect_choices=(
            ["错误答案B", "错误答案C", "错误答案D"]
            if q_type == QuestionTypeEnum.SINGLE_CHOICE
            else None
        ),
        standard_answer_text=(
            "主观题参考答案" if q_type == QuestionTypeEnum.ESSAY_QUESTION else None
        ),
        ref="答案解析",
    )


@pytest.mark.asyncio
async def test_create_new_paper_success(
    paper_crud_instance: PaperCRUD,
    mock_qb_crud: AsyncMock,
    mock_repo: AsyncMock,
    mock_request: MagicMock,
):
    """测试 create_new_paper 成功创建试卷的场景。"""
    user_uid = "test_user_create_paper"
    difficulty = DifficultyLevel.easy
    num_questions = 5

    mock_questions = [_create_mock_question(f"q{i + 1}") for i in range(num_questions)]
    mock_qb_crud.get_questions_for_paper.return_value = mock_questions

    async def mock_create_effect(entity_type, data):
        assert entity_type == PAPER_ENTITY_TYPE
        return {
            **data,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    mock_repo.create.side_effect = mock_create_effect

    result = await paper_crud_instance.create_new_paper(
        request=mock_request,
        user_uid=user_uid,
        difficulty=difficulty,
        num_questions_override=num_questions,
    )

    assert result is not None
    assert result["paper_id"] is not None
    assert result["difficulty"] == difficulty.value
    assert len(result["paper"]) == num_questions

    mock_qb_crud.get_questions_for_paper.assert_called_once_with(
        difficulty, num_questions
    )
    mock_repo.create.assert_called_once()

    created_paper_data = mock_repo.create.call_args[0][1]
    assert created_paper_data["user_uid"] == user_uid
    assert created_paper_data["difficulty"] == difficulty.value
    assert len(created_paper_data["paper_questions"]) == num_questions
    assert created_paper_data["status"] == PaperStatusEnum.IN_PROGRESS.value


@pytest.mark.asyncio
async def test_create_new_paper_not_enough_questions(
    paper_crud_instance: PaperCRUD, mock_qb_crud: AsyncMock, mock_request: MagicMock
):
    """测试当题库题目不足时 create_new_paper 引发 ValueError。"""
    user_uid = "test_user_no_questions"
    difficulty = DifficultyLevel.hard
    num_questions = 10

    mock_questions = [_create_mock_question(f"hq{i + 1}") for i in range(5)]
    mock_qb_crud.get_questions_for_paper.return_value = mock_questions

    with pytest.raises(ValueError) as exc_info:
        await paper_crud_instance.create_new_paper(
            request=mock_request,
            user_uid=user_uid,
            difficulty=difficulty,
            num_questions_override=num_questions,
        )
    assert "题库题目不足" in str(exc_info.value) or "Not enough questions" in str(
        exc_info.value
    )


# endregion

# region get_paper_by_id 测试 (get_paper_by_id Tests)


@pytest.mark.asyncio
async def test_get_paper_by_id_found(
    paper_crud_instance: PaperCRUD, mock_repo: AsyncMock
):
    """测试 get_paper_by_id 在试卷存在时返回 PaperInDB 实例。"""
    paper_id = str(uuid.uuid4())
    paper_data_from_repo = {
        "paper_id": paper_id,
        "user_uid": TEST_USER_UID,
        "difficulty": DifficultyLevel.easy.value,
        "status": PaperStatusEnum.IN_PROGRESS.value,
        "paper_questions": [],
        "answers": {},
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    mock_repo.get_by_id.return_value = paper_data_from_repo

    paper = await paper_crud_instance.get_paper_by_id(paper_id, TEST_USER_UID)

    assert paper is not None
    assert isinstance(paper, PaperInDB)
    assert paper.paper_id == paper_id
    mock_repo.get_by_id.assert_called_once_with(PAPER_ENTITY_TYPE, paper_id)


# endregion

# region update_paper_progress 测试 (update_paper_progress Tests)


@pytest.mark.asyncio
async def test_update_paper_progress_success(
    paper_crud_instance: PaperCRUD,
    mock_repo: AsyncMock,
    mock_request: MagicMock,
    mocker,
):
    """测试 update_paper_progress 成功更新答题进度。"""
    paper_id = str(uuid.uuid4())
    user_uid = TEST_USER_UID

    original_paper = PaperInDB(
        paper_id=paper_id,
        user_uid=user_uid,
        difficulty=DifficultyLevel.easy,
        status=PaperStatusEnum.IN_PROGRESS,
        paper_questions=[
            PaperQuestionInternalDetail(**_create_mock_question("q1").model_dump()),
            PaperQuestionInternalDetail(**_create_mock_question("q2").model_dump()),
        ],
        answers={},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    mocker.patch.object(
        paper_crud_instance, "get_paper_by_id", return_value=original_paper
    )

    async def mock_update_effect(entity_type, pid, data_to_update):
        assert "answers" in data_to_update
        assert "updated_at" in data_to_update
        return {**original_paper.model_dump(), **data_to_update}

    mock_repo.update.side_effect = mock_update_effect

    q1_internal_id = original_paper.paper_questions[0].internal_id
    answers_payload = {q1_internal_id: "答案A"}

    result = await paper_crud_instance.update_paper_progress(
        paper_id, user_uid, answers_payload, mock_request
    )

    assert result["status_code"] == "PROGRESS_SAVED"
    assert result["message"] == "答题进度已保存。"

    paper_crud_instance.get_paper_by_id.assert_called_once_with(paper_id, user_uid)
    mock_repo.update.assert_called_once()
    update_args = mock_repo.update.call_args[0][2]
    assert q1_internal_id in update_args["answers"]
    assert update_args["answers"][q1_internal_id] == "答案A"


# endregion

# region grade_paper_submission 测试 (grade_paper_submission Tests)


@pytest.mark.asyncio
async def test_grade_paper_submission_pass(
    paper_crud_instance: PaperCRUD,
    mock_repo: AsyncMock,
    mock_request: MagicMock,
    mocker,
):
    """测试 grade_paper_submission 对于通过考试的场景。"""
    paper_id = str(uuid.uuid4())
    user_uid = TEST_USER_UID

    mock_q1 = _create_mock_question(
        "q1_id", body="题目1", q_type=QuestionTypeEnum.SINGLE_CHOICE
    )
    mock_q1.correct_choices = ["A"]
    mock_q2 = _create_mock_question(
        "q2_id", body="题目2", q_type=QuestionTypeEnum.SINGLE_CHOICE
    )
    mock_q2.correct_choices = ["B"]

    paper_questions_internal = [
        PaperQuestionInternalDetail(**mock_q1.model_dump(), score_value=50),
        PaperQuestionInternalDetail(**mock_q2.model_dump(), score_value=50),
    ]

    original_paper = PaperInDB(
        paper_id=paper_id,
        user_uid=user_uid,
        difficulty=DifficultyLevel.easy,
        status=PaperStatusEnum.IN_PROGRESS,
        paper_questions=paper_questions_internal,
        answers={},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    mocker.patch.object(
        paper_crud_instance, "get_paper_by_id", return_value=original_paper
    )

    async def mock_grade_update_effect(entity_type, pid, data_to_update):
        return {**original_paper.model_dump(), **data_to_update}

    mock_repo.update.side_effect = mock_grade_update_effect

    submitted_answers = {
        paper_questions_internal[0].internal_id: "A",
        paper_questions_internal[1].internal_id: "B",
    }

    grading_outcome = await paper_crud_instance.grade_paper_submission(
        paper_id, user_uid, submitted_answers, mock_request
    )

    assert grading_outcome["status_code"] == "PASSED"
    assert grading_outcome["total_score_obtained"] == 100
    assert grading_outcome["score_percentage"] == 100.0
    assert grading_outcome["pass_status"] is True
    assert grading_outcome["passcode"] is not None

    mock_repo.update.assert_called_once()
    update_args = mock_repo.update.call_args[0][2]
    assert update_args["status"] == PaperStatusEnum.COMPLETED.value
    assert update_args["pass_status"] is True
    assert update_args["answers"] == submitted_answers
    for pq_updated in update_args["paper_questions"]:
        assert pq_updated["score_obtained"] == pq_updated["score_value"]


# endregion


# region 主观题评分测试 (Subjective Question Grading Tests)
@pytest.mark.asyncio
async def test_grade_subjective_question_success(
    paper_crud_instance: PaperCRUD, mock_repo: AsyncMock, mocker
):
    """测试 grade_subjective_question 成功更新主观题得分和评语。"""
    paper_id_uuid = uuid.uuid4()
    paper_id = str(paper_id_uuid)
    user_uid = "subjective_test_user"

    q_subjective_internal_id = str(uuid.uuid4())
    subjective_question_detail = PaperQuestionInternalDetail(
        internal_id=q_subjective_internal_id,
        id="subj_q1",
        question_type=QuestionTypeEnum.ESSAY_QUESTION,
        body="请论述...",
        score_value=20,
    )
    original_paper = PaperInDB(
        paper_id=paper_id,
        user_uid=user_uid,
        difficulty=DifficultyLevel.hybrid,
        status=PaperStatusEnum.PENDING_MANUAL_GRADING,
        paper_questions=[subjective_question_detail],
        answers={q_subjective_internal_id: "这是学生的答案..."},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    mocker.patch.object(
        paper_crud_instance, "get_paper_by_id", return_value=original_paper
    )

    mock_repo.update.return_value = True

    manual_score = 15
    teacher_comment = "论述清晰，但缺乏实例。"

    success = await paper_crud_instance.grade_subjective_question(
        paper_id=paper_id_uuid,
        question_internal_id=q_subjective_internal_id,
        manual_score=manual_score,
        teacher_comment=teacher_comment,
    )

    assert success is True
    mock_repo.update.assert_called_once()

    update_args = mock_repo.update.call_args[0][2]
    assert "paper_questions" in update_args

    updated_sq = next(
        (
            q
            for q in update_args["paper_questions"]
            if q["internal_id"] == q_subjective_internal_id
        ),
        None,
    )
    assert updated_sq is not None
    assert updated_sq["score_obtained"] == manual_score
    assert updated_sq["teacher_comment"] == teacher_comment
    assert updated_sq["is_graded"] is True


# endregion
