# -*- coding: utf-8 -*-
"""
app.crud.qb.QuestionBankCRUD 类的单元测试。
(Unit tests for the app.crud.qb.QuestionBankCRUD class.)
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional  # F821: For type hints
from unittest.mock import mock_open

import pytest

from app.core.config import (
    Settings,
)  # 导入Settings以模拟
from app.crud.qb import QuestionBankCRUD
from app.models.enums import (
    DifficultyLevel,
    QuestionTypeEnum,  # Added for _create_mock_question
)
from app.models.qb_models import (
    LibraryIndexItem,
    QuestionBank,
    QuestionModel,
)  # Added QuestionModel for _create_mock_question

# region Fixtures (测试固件)


@pytest.fixture
def mock_settings(tmp_path: Path) -> Settings:
    """提供一个模拟的 Settings 对象，其中包含测试用的题库路径。"""
    # 创建临时的 data/library 目录结构
    # (Create temporary data/library directory structure)
    data_dir = tmp_path / "data"
    library_dir = data_dir / "library"
    library_dir.mkdir(parents=True, exist_ok=True)

    # 创建一个模拟的 settings.json 内容 (如果需要)
    # (Create mock settings.json content (if needed))
    # settings_json_path = data_dir / "settings.json"
    # settings_json_path.write_text(json.dumps({
    #     "question_library_path": "library",
    #     "question_library_index_file": "index.json"
    # }))

    # 返回一个配置好的Settings实例
    # (Return a configured Settings instance)
    # 注意: QuestionBankCRUD 的 __init__ 并没有直接接收 settings 对象，
    # 而是假设 settings 已经被加载并在模块级别可用 (from app.core.config import settings)。
    # 因此，对 settings 的 mock 需要通过 mocker.patch 来进行。
    # 这里我们创建一个真实的Settings对象，然后用mocker去patch全局的settings。
    # (Note: QuestionBankCRUD's __init__ doesn't directly take a settings object,
    #  it assumes settings are loaded and available at module level.
    #  So, mocking settings needs mocker.patch.
    #  Here we create a real Settings object, then use mocker to patch the global one.)

    # 使用默认值，但确保路径指向tmp_path (Use defaults, but ensure paths point to tmp_path)
    s = Settings(
        data_dir=data_dir,  # 设置 data_dir
        question_library_path="library",  # 相对于 data_dir (Relative to data_dir)
        question_library_index_file="index.json",
        # 可以根据需要填充其他Settings字段 (Can fill other Settings fields as needed)
    )
    return s


@pytest.fixture
def qb_crud_instance(mocker, mock_settings: Settings) -> QuestionBankCRUD:
    """
    提供一个 QuestionBankCRUD 实例。
    它会模拟全局的 `settings` 对象，并使用 `tmp_path` 进行文件操作。
    """
    # 使用 mocker.patch.object 来替换模块中导入的 settings 实例
    # (Use mocker.patch.object to replace the imported settings instance in the module)
    mocker.patch("app.crud.qb.settings", mock_settings)

    # QuestionBankCRUD 内部也可能使用 repository_instance 进行锁管理
    # (QuestionBankCRUD might also use repository_instance for lock management)
    # 如果是这样，我们也需要模拟它。当前的 qb.py 实现似乎没有直接使用通用 repository_instance。
    # (If so, we need to mock it too. Current qb.py impl doesn't seem to use generic repo.)

    # 对于锁，QuestionBankCRUD 使用全局锁字典 _qb_locks 和 asyncio.Lock()
    # (For locks, QuestionBankCRUD uses a global lock dict _qb_locks and asyncio.Lock())
    # 我们不需要显式模拟这些，除非测试并发场景。
    # (We don't need to explicitly mock these unless testing concurrent scenarios.)

    # 清理可能由其他测试遗留的锁 (Clean up locks possibly left over from other tests)
    from app.crud.qb import _qb_locks

    _qb_locks.clear()

    return QuestionBankCRUD()


# 辅助函数，用于创建模拟的题库JSON文件内容
# (Helper function to create mock question bank JSON file content)
def create_mock_qb_file_content(num_questions: int, difficulty_id: str) -> str:
    questions = []
    for i in range(num_questions):
        q_id = f"{difficulty_id}_q{i + 1}"
        questions.append(
            {
                "id": q_id,  # Nuitka build/PaperCRUD expects QuestionModel to have an 'id'
                "body": f"{difficulty_id} 题目内容 {i + 1} (Question body {i + 1})",
                "question_type": "SINGLE_CHOICE",
                "correct_choices": [f"答案A_{i + 1}"],
                "incorrect_choices": [
                    f"答案B_{i + 1}",
                    f"答案C_{i + 1}",
                    f"答案D_{i + 1}",
                ],
                "ref": f"解析 {i + 1}",
            }
        )
    return json.dumps(questions)


def create_mock_index_file_content(libraries: List[Dict[str, Any]]) -> str:
    return json.dumps(libraries)


# Duplicating _create_mock_question from test_paper_crud.py for now
# Ideally, this would be in a shared test utils file.
# Copied from tests/crud/test_paper_crud.py and adjusted to include its own QuestionModel import
def _create_mock_question(
    q_id: str,
    q_type: QuestionTypeEnum = QuestionTypeEnum.SINGLE_CHOICE,
    body: str = "题目内容",
    difficulty_id: Optional[str] = None,
) -> QuestionModel:
    """辅助函数：创建模拟题目模型。"""
    # Add difficulty_id to the mock question id if provided, for hybrid test differentiation.
    effective_q_id = f"{difficulty_id}_{q_id}" if difficulty_id else q_id
    return QuestionModel(
        id=effective_q_id,
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


# endregion

# region initialize_question_banks 测试 (initialize_question_banks Tests)


@pytest.mark.asyncio
async def test_initialize_question_banks_success(
    qb_crud_instance: QuestionBankCRUD, mock_settings: Settings, mocker
):
    """测试 initialize_question_banks 成功加载题库索引和文件。"""
    # 准备模拟的 index.json 内容
    # (Prepare mock index.json content)
    mock_index_content = create_mock_index_file_content(
        [
            {
                "id": "easy",
                "name": "简单",
                "default_questions": 3,
                "total_questions": 0,
            },  # total_questions 会被更新 (will be updated)
            {
                "id": "hard",
                "name": "困难",
                "default_questions": 2,
                "total_questions": 0,
            },
        ]
    )

    # 准备模拟的 easy.json 和 hard.json 内容
    # (Prepare mock easy.json and hard.json content)
    mock_easy_content = create_mock_qb_file_content(
        5, "easy"
    )  # 5道简单题 (5 easy questions)
    mock_hard_content = create_mock_qb_file_content(
        3, "hard"
    )  # 3道难题 (3 hard questions)

    # 使用 mocker.patch 模拟 open 函数的行为
    # (Use mocker.patch to simulate open function behavior)
    def mock_open_side_effect(file_path_obj, mode="r", encoding=None):
        file_path_str = str(file_path_obj)  # Path 对象转字符串 (Path object to string)
        if file_path_str.endswith("index.json"):
            return mocker.mock_open(read_data=mock_index_content).return_value
        elif file_path_str.endswith("easy.json"):
            return mocker.mock_open(read_data=mock_easy_content).return_value
        elif file_path_str.endswith("hard.json"):
            return mocker.mock_open(read_data=mock_hard_content).return_value
        else:
            # 对于未预期的文件路径，抛出 FileNotFoundError
            # (For unexpected file paths, raise FileNotFoundError)
            raise FileNotFoundError(f"测试中未预期的文件访问: {file_path_str}")

    mocker.patch("builtins.open", side_effect=mock_open_side_effect)

    # Path.exists() 需要返回 True (Path.exists() needs to return True)
    mock_path_exists = mocker.patch("pathlib.Path.exists")
    mock_path_exists.return_value = True

    # Path.is_file() 也需要返回 True (Path.is_file() also needs to return True)
    mock_path_is_file = mocker.patch("pathlib.Path.is_file")
    mock_path_is_file.return_value = True

    await qb_crud_instance.initialize_question_banks()

    assert len(qb_crud_instance._library_index) == 2, "题库索引加载数量不正确。"
    assert DifficultyLevel.easy.value in qb_crud_instance._question_banks, (
        "简单题库未加载。"
    )
    assert (
        len(qb_crud_instance._question_banks[DifficultyLevel.easy.value].questions) == 5
    ), "简单题库题目数量不正确。"
    assert DifficultyLevel.hard.value in qb_crud_instance._question_banks, (
        "困难题库未加载。"
    )
    assert (
        len(qb_crud_instance._question_banks[DifficultyLevel.hard.value].questions) == 3
    ), "困难题库题目数量不正确。"

    # 检查 total_questions 是否已更新 (Check if total_questions is updated)
    easy_index_item = next(
        item
        for item in qb_crud_instance._library_index
        if item.id == DifficultyLevel.easy.value
    )
    assert easy_index_item.total_questions == 5, (
        "简单题库索引中的 total_questions 未更新。"
    )


@pytest.mark.asyncio
async def test_initialize_question_banks_index_file_missing(
    qb_crud_instance: QuestionBankCRUD, mock_settings: Settings, mocker
):
    """测试当 index.json 文件缺失时的初始化行为。"""

    # 模拟 Path.exists() 对 index.json 返回 False
    # (Simulate Path.exists() returns False for index.json)
    def path_exists_side_effect(path_obj):
        if str(path_obj).endswith("index.json"):
            return False
        return True  # 其他文件假设存在 (Assume other files exist)

    mocker.patch("pathlib.Path.exists", side_effect=path_exists_side_effect)
    mocker.patch(
        "pathlib.Path.is_file", return_value=True
    )  # 假设其他路径是文件 (Assume other paths are files)

    # 不需要模拟 open，因为文件不存在时不会尝试打开
    # (No need to mock open, as it won't be called if file doesn't exist)

    await qb_crud_instance.initialize_question_banks()

    assert not qb_crud_instance._library_index, (
        "索引文件缺失时，_library_index 应为空。"
    )
    assert not qb_crud_instance._question_banks, (
        "索引文件缺失时，_question_banks 应为空。"
    )


@pytest.mark.asyncio
async def test_initialize_question_banks_bank_file_corrupted(
    qb_crud_instance: QuestionBankCRUD, mock_settings: Settings, mocker
):
    """测试当某个题库文件 (如 easy.json) 内容损坏 (无效JSON) 时的处理。"""
    mock_index_content = create_mock_index_file_content(
        [{"id": "easy", "name": "简单", "default_questions": 3}]
    )
    corrupted_easy_content = "这不是一个有效的JSON (This is not valid JSON)"

    def mock_open_side_effect(file_path_obj, mode="r", encoding=None):
        file_path_str = str(file_path_obj)
        if file_path_str.endswith("index.json"):
            return mocker.mock_open(read_data=mock_index_content).return_value
        elif file_path_str.endswith("easy.json"):
            return mocker.mock_open(read_data=corrupted_easy_content).return_value
        raise FileNotFoundError(f"测试中未预期的文件访问: {file_path_str}")

    mocker.patch("builtins.open", side_effect=mock_open_side_effect)
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("pathlib.Path.is_file", return_value=True)

    await qb_crud_instance.initialize_question_banks()

    assert len(qb_crud_instance._library_index) == 1, "题库索引应已加载。"
    # 损坏的题库文件不应加载到 _question_banks 中
    # (Corrupted bank file should not be loaded into _question_banks)
    assert DifficultyLevel.easy.value not in qb_crud_instance._question_banks, (
        "损坏的easy题库不应被加载。"
    )
    # 索引中的 total_questions 应该为0或未被更新为有效值
    # (total_questions in index should be 0 or not updated to a valid value)
    easy_index_item = next(
        item
        for item in qb_crud_instance._library_index
        if item.id == DifficultyLevel.easy.value
    )
    assert easy_index_item.total_questions == 0, "损坏题库的 total_questions 应为0。"


# endregion


# region get_question_bank_with_content 测试 (get_question_bank_with_content Tests)
@pytest.mark.asyncio
async def test_get_question_bank_with_content_found(
    qb_crud_instance: QuestionBankCRUD, mocker
):
    """测试 get_question_bank_with_content 成功找到并返回题库。"""
    # 手动填充内部状态以进行测试 (Manually populate internal state for testing)
    difficulty = DifficultyLevel.easy
    mock_bank_data = QuestionBank(
        metadata=LibraryIndexItem(
            id=difficulty.value,
            name="简单题库",
            default_questions=5,
            total_questions=10,
        ),
        questions=[_create_mock_question(f"q{i}") for i in range(10)],
    )
    qb_crud_instance._question_banks[difficulty.value] = mock_bank_data

    bank = await qb_crud_instance.get_question_bank_with_content(difficulty)

    assert bank is not None, "未能获取题库内容。"
    assert bank.metadata.id == difficulty.value, "返回的题库元数据ID不正确。"
    assert len(bank.questions) == 10, "返回的题库题目数量不正确。"


@pytest.mark.asyncio
async def test_get_question_bank_with_content_not_found(
    qb_crud_instance: QuestionBankCRUD,
):
    """测试 get_question_bank_with_content 在题库不存在时返回 None。"""
    # 确保请求的题库不在内部状态中 (Ensure requested bank is not in internal state)
    qb_crud_instance._question_banks.clear()

    bank = await qb_crud_instance.get_question_bank_with_content(DifficultyLevel.hard)

    assert bank is None, "对于不存在的题库，应返回 None。"


# endregion


# region get_all_library_metadatas 测试 (get_all_library_metadatas Tests)
@pytest.mark.asyncio
async def test_get_all_library_metadatas(qb_crud_instance: QuestionBankCRUD):
    """测试 get_all_library_metadatas 返回正确的元数据列表。"""
    mock_metadata = [
        LibraryIndexItem(
            id="easy", name="简单", default_questions=5, total_questions=10
        ),
        LibraryIndexItem(
            id="hard", name="困难", default_questions=3, total_questions=8
        ),
    ]
    qb_crud_instance._library_index = (
        mock_metadata  # 直接设置内部状态 (Directly set internal state)
    )

    metadatas = await qb_crud_instance.get_all_library_metadatas()

    assert len(metadatas) == 2, "返回的元数据列表长度不正确。"
    assert metadatas[0].name == "简单", "元数据内容不匹配。"


# endregion

# region get_questions_for_paper 测试 (get_questions_for_paper Tests)


@pytest.mark.asyncio
async def test_get_questions_for_paper_success(
    qb_crud_instance: QuestionBankCRUD, mocker
):
    """测试 get_questions_for_paper 成功获取指定数量的题目。"""
    difficulty = DifficultyLevel.easy
    num_questions_to_get = 3
    # 准备一个包含足够题目的模拟题库 (Prepare a mock bank with enough questions)
    mock_bank_questions = [_create_mock_question(f"easy_q{i}") for i in range(10)]
    qb_crud_instance._question_banks[difficulty.value] = QuestionBank(
        metadata=LibraryIndexItem(
            id=difficulty.value, name="Easy", default_questions=10, total_questions=10
        ),
        questions=mock_bank_questions,
    )

    # 如果内部使用了 random.sample, 可以 mock 它来获得确定性结果
    # (If random.sample is used internally, can mock it for deterministic results)
    mocker.patch("random.sample", side_effect=lambda population, k: population[:k])

    questions = await qb_crud_instance.get_questions_for_paper(
        difficulty, num_questions_to_get
    )

    assert len(questions) == num_questions_to_get, "获取到的题目数量不正确。"
    # 更多断言，例如题目是否来自正确的题库，是否唯一等
    # (More assertions, e.g., if questions are from correct bank, if they are unique, etc.)


@pytest.mark.asyncio
async def test_get_questions_for_paper_not_enough_questions(
    qb_crud_instance: QuestionBankCRUD, mocker
):
    """测试 get_questions_for_paper 在题目不足时引发 ValueError。"""
    difficulty = DifficultyLevel.medium
    num_questions_to_get = 10
    # 题库中只有5道题 (Only 5 questions in bank)
    mock_bank_questions = [_create_mock_question(f"medium_q{i}") for i in range(5)]
    qb_crud_instance._question_banks[difficulty.value] = QuestionBank(
        metadata=LibraryIndexItem(
            id=difficulty.value, name="Medium", default_questions=5, total_questions=5
        ),
        questions=mock_bank_questions,
    )

    with pytest.raises(ValueError) as exc_info:
        await qb_crud_instance.get_questions_for_paper(difficulty, num_questions_to_get)
    assert "题库题目不足" in str(exc_info.value) or "Not enough questions" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_get_questions_for_paper_hybrid_difficulty(
    qb_crud_instance: QuestionBankCRUD, mocker
):
    """测试混合难度 (hybrid) 的 get_questions_for_paper 逻辑。"""
    num_hybrid_questions = 10
    # 准备简单和困难题库 (Prepare easy and hard banks)
    easy_questions = [
        _create_mock_question(f"easy_h_q{i}", difficulty_id="easy") for i in range(7)
    ]
    hard_questions = [
        _create_mock_question(f"hard_h_q{i}", difficulty_id="hard") for i in range(7)
    ]

    qb_crud_instance._question_banks[DifficultyLevel.easy.value] = QuestionBank(
        metadata=LibraryIndexItem(
            id="easy", name="Easy", default_questions=7, total_questions=7
        ),
        questions=easy_questions,
    )
    qb_crud_instance._question_banks[DifficultyLevel.hard.value] = QuestionBank(
        metadata=LibraryIndexItem(
            id="hard", name="Hard", default_questions=7, total_questions=7
        ),
        questions=hard_questions,
    )
    # 确保混合难度配置存在于 _library_index (Ensure hybrid difficulty config exists in _library_index)
    qb_crud_instance._library_index = [
        LibraryIndexItem(
            id="easy", name="Easy", default_questions=7, total_questions=7
        ),
        LibraryIndexItem(
            id="hard", name="Hard", default_questions=7, total_questions=7
        ),
        LibraryIndexItem(
            id="hybrid", name="Hybrid", default_questions=10, total_questions=0
        ),  # total_questions for hybrid is not directly used
    ]

    # 模拟 random.sample (Simulate random.sample)
    mocker.patch("random.sample", side_effect=lambda population, k: population[:k])

    questions = await qb_crud_instance.get_questions_for_paper(
        DifficultyLevel.hybrid, num_hybrid_questions
    )

    assert len(questions) == num_hybrid_questions, "混合难度获取的题目数量不正确。"
    # 检查题目是否来自不同难度 (Check if questions are from different difficulties)
    # 混合逻辑是各取一半，向上取整 (Hybrid logic is half from each, ceiling)
    easy_count = sum(1 for q in questions if q.id.startswith("easy"))
    hard_count = sum(1 for q in questions if q.id.startswith("hard"))

    assert easy_count == num_hybrid_questions // 2 + (
        num_hybrid_questions % 2
    )  # 5 for 10
    assert hard_count == num_hybrid_questions // 2  # 5 for 10


# endregion

# region add_question_to_bank 和 delete_question_from_bank 测试
# (add_question_to_bank and delete_question_from_bank Tests)
# 这些测试较为复杂，因为它们涉及到文件I/O的模拟。
# (These tests are more complex as they involve mocking file I/O.)


@pytest.mark.asyncio
async def test_add_question_to_bank_success(
    qb_crud_instance: QuestionBankCRUD, mock_settings: Settings, mocker
):
    """测试 add_question_to_bank 成功添加题目并模拟文件保存。"""
    difficulty = DifficultyLevel.easy
    # 先初始化一个空的或已有的easy题库 (Initialize an empty or existing easy bank first)
    initial_easy_questions = [_create_mock_question("easy_q_orig")]
    qb_crud_instance._question_banks[difficulty.value] = QuestionBank(
        metadata=LibraryIndexItem(
            id=difficulty.value, name="Easy", default_questions=1, total_questions=1
        ),
        questions=initial_easy_questions,
    )
    qb_crud_instance._library_index = [
        LibraryIndexItem(
            id=difficulty.value, name="Easy", default_questions=1, total_questions=1
        )
    ]

    new_question_data = _create_mock_question("easy_q_new", body="新添加的题目")

    # 模拟文件写入 (Simulate file writing)
    mock_file_open = mocker.patch("builtins.open", mock_open())
    # 模拟json.dump (Simulate json.dump)
    mock_json_dump = mocker.patch("json.dump")

    added_question_model = await qb_crud_instance.add_question_to_bank(
        difficulty, new_question_data
    )

    assert added_question_model.body == "新添加的题目", "返回的题目内容不正确。"
    assert len(qb_crud_instance._question_banks[difficulty.value].questions) == 2, (
        "题目未添加到内存中的题库。"
    )

    # 验证文件是否被尝试写入 (Verify if file was attempted to be written)
    expected_file_path = (
        mock_settings.data_dir
        / mock_settings.question_library_path
        / f"{difficulty.value}.json"
    )
    mock_file_open.assert_called_once_with(expected_file_path, "w", encoding="utf-8")
    # 验证json.dump是否用正确的数据调用 (Verify json.dump was called with correct data)
    # json.dump的第一个参数是obj，第二个是fp (json.dump's first arg is obj, second is fp)
    dump_args = mock_json_dump.call_args[0][0]
    assert (
        len(dump_args) == 2
    )  # 包含原始题目和新题目 (Contains original and new question)
    assert any(q["body"] == "新添加的题目" for q in dump_args), (
        "新题目未包含在待写入数据中。"
    )

    # 验证索引中的 total_questions 是否更新 (Verify total_questions in index is updated)
    easy_index_item = next(
        item for item in qb_crud_instance._library_index if item.id == difficulty.value
    )
    assert easy_index_item.total_questions == 2, "索引中题库总数未更新。"


@pytest.mark.asyncio
async def test_delete_question_from_bank_success(
    qb_crud_instance: QuestionBankCRUD, mock_settings: Settings, mocker
):
    """测试 delete_question_from_bank 成功删除题目并模拟文件保存。"""
    difficulty = DifficultyLevel.hard
    question_to_delete_id = "hard_q2_del"
    initial_hard_questions = [
        _create_mock_question("hard_q1"),
        _create_mock_question(question_to_delete_id, body="待删除题目"),
        _create_mock_question("hard_q3"),
    ]
    qb_crud_instance._question_banks[difficulty.value] = QuestionBank(
        metadata=LibraryIndexItem(
            id=difficulty.value, name="Hard", default_questions=3, total_questions=3
        ),
        questions=initial_hard_questions,
    )
    qb_crud_instance._library_index = [
        LibraryIndexItem(
            id=difficulty.value, name="Hard", default_questions=3, total_questions=3
        )
    ]

    # 模拟文件写入和json.dump
    mock_file_open = mocker.patch("builtins.open", mock_open())
    mock_json_dump = mocker.patch("json.dump")

    # QuestionBankCRUD.delete_question_from_bank 期望的是题目在列表中的索引，而不是ID
    # (QuestionBankCRUD.delete_question_from_bank expects index in list, not ID)
    # 我们需要找到待删除题目的索引 (We need to find index of question to delete)
    idx_to_delete = -1
    for i, q in enumerate(initial_hard_questions):
        if (
            q.id == question_to_delete_id
        ):  # 'id' is an attribute of QuestionModel after _create_mock_question
            idx_to_delete = i
            break

    assert idx_to_delete != -1, "测试设置错误：待删除题目ID未在初始列表中找到。"

    deleted_question_model_dict = await qb_crud_instance.delete_question_from_bank(
        difficulty, idx_to_delete
    )

    assert deleted_question_model_dict is not None, "删除操作未返回已删除的题目数据。"
    assert deleted_question_model_dict["body"] == "待删除题目", (
        "返回的已删除题目内容不正确。"
    )
    assert len(qb_crud_instance._question_banks[difficulty.value].questions) == 2, (
        "题目未从内存题库中删除。"
    )
    assert not any(
        q.id == question_to_delete_id
        for q in qb_crud_instance._question_banks[difficulty.value].questions
    ), "已删除的题目仍存在于内存中。"

    expected_file_path = (
        mock_settings.data_dir
        / mock_settings.question_library_path
        / f"{difficulty.value}.json"
    )
    mock_file_open.assert_called_once_with(expected_file_path, "w", encoding="utf-8")
    dump_args = mock_json_dump.call_args[0][0]
    assert len(dump_args) == 2, "写入文件的题目数量不正确。"
    assert not any(q["body"] == "待删除题目" for q in dump_args), (
        "已删除的题目仍包含在待写入数据中。"
    )

    hard_index_item = next(
        item for item in qb_crud_instance._library_index if item.id == difficulty.value
    )
    assert hard_index_item.total_questions == 2, "索引中题库总数未更新。"


# endregion
