# -*- coding: utf-8 -*-
"""
共享枚举类型模块。
(Shared Enumeration Types Module.)

此模块定义了在整个应用中可能被多个模块复用的枚举类型。
(This module defines enumeration types that may be reused by multiple modules
across the application.)
"""

from enum import Enum
import json # ADDED
import logging # ADDED
from pathlib import Path # ADDED
from typing import List # ADDED

_enums_module_logger = logging.getLogger(__name__) # ADDED

# region 动态难度级别枚举定义 (Dynamic DifficultyLevel Enum Definition) - MOVED FROM config.py

def _get_difficulty_ids_from_index_json() -> List[str]:
    """
    从题库索引文件 (data/library/index.json) 读取并提取唯一的 'id' 值，
    用于动态创建 `DifficultyLevel` 枚举的成员。
    此函数在模块加载时被调用一次。

    (Reads and extracts unique 'id' values from the question bank index file
    (data/library/index.json) to dynamically create members for the `DifficultyLevel` enum.
    This function is called once when the module is loaded.)

    返回 (Returns):
        List[str]: 从索引文件中提取的有效且唯一的难度ID列表。
                   如果文件不存在、格式错误或未找到有效ID，则返回空列表。
                   (A list of valid and unique difficulty IDs extracted from the index file.
                    Returns an empty list if the file does not exist, is improperly formatted,
                    or no valid IDs are found.)
    """
    ids: List[str] = []
    try:
        # 获取当前工作目录，并构建数据和题库索引文件的路径
        # (Get current working directory and construct paths for data and library index files)
        base_data_path = Path.cwd() / "data"
        library_path_default = "library"  # 题库目录名 (Question library directory name)
        index_file_default = (
            "index.json"  # 题库索引文件名 (Question library index file name)
        )
        index_json_path = base_data_path / library_path_default / index_file_default

        if not index_json_path.exists():
            _enums_module_logger.error(
                f"DifficultyLevel: 关键文件 '{index_json_path}' 未找到。"
                "无法从题库索引动态创建 DifficultyLevel 枚举。"
                "(DifficultyLevel: Critical file '{index_json_path}' not found. "
                "Cannot dynamically create DifficultyLevel enum from library index.)"
            )
            return []

        with open(index_json_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)  # 加载JSON数据 (Load JSON data)

        if not isinstance(index_data, list):
            _enums_module_logger.error(
                f"DifficultyLevel: 文件 '{index_json_path}' 的内容不是一个列表。"
                "期望的是一个包含题库元数据项的列表。"
                "(DifficultyLevel: Content of file '{index_json_path}' is not a list. "
                "Expected a list of question bank metadata items.)"
            )
            return []

        for item_idx, item in enumerate(index_data):
            if isinstance(item, dict) and "id" in item and isinstance(item["id"], str):
                item_id = item["id"]
                if not item_id:  # ID不应为空 (ID should not be empty)
                    _enums_module_logger.warning(
                        f"DifficultyLevel: 文件 '{index_json_path}' 中索引 {item_idx} 处的项目 'id' 为空。已跳过。"
                        f"(DifficultyLevel: Item at index {item_idx} in '{index_json_path}' has an empty 'id'. Skipped.)"
                    )
                    continue
                if (
                    not item_id.isidentifier()
                ):  # ID必须是有效的Python标识符 (ID must be a valid Python identifier)
                    _enums_module_logger.error(
                        f"DifficultyLevel: 文件 '{index_json_path}' 中的项目 'id' \"{item_id}\" 不是有效的Python标识符。不能用作枚举成员名。已跳过。"
                        f"(DifficultyLevel: Item 'id' \"{item_id}\" in '{index_json_path}' is not a valid Python identifier. Cannot be used as enum member name. Skipped.)"
                    )
                    continue
                if item_id not in ids:  # 保证ID的唯一性 (Ensure uniqueness of ID)
                    ids.append(item_id)
                else:  # 如果重复，记录警告并使用第一个 (If duplicate, log warning and use the first occurrence)
                    _enums_module_logger.warning(
                        f"DifficultyLevel: 在 '{index_json_path}' 中发现重复的 'id' \"{item_id}\"。将使用首次出现的值。"
                        f"(DifficultyLevel: Duplicate 'id' \"{item_id}\" found in '{index_json_path}'. Using the first occurrence.)"
                    )
            else:
                _enums_module_logger.warning(
                    f"DifficultyLevel: 文件 '{index_json_path}' 中索引 {item_idx} 处的项目无效或缺少有效的 'id' 字符串: {str(item)[:100]}..."
                    f"(DifficultyLevel: Item at index {item_idx} in '{index_json_path}' is invalid or lacks a valid 'id' string: {str(item)[:100]}...)"
                )

        if (
            not ids
        ):  # 如果最终没有收集到任何有效的ID (If no valid IDs were collected in the end)
            _enums_module_logger.warning(
                f"DifficultyLevel: 未能在 '{index_json_path}' 中找到任何有效且唯一的 'id' 来创建 DifficultyLevel 枚举成员。"
                f"(DifficultyLevel: Failed to find any valid and unique 'id' in '{index_json_path}' to create DifficultyLevel enum members.)"
            )
        return ids
    except json.JSONDecodeError as e:
        _enums_module_logger.error(
            f"DifficultyLevel: 从 '{index_json_path}' 解码JSON失败: {e}。无法创建动态 DifficultyLevel 枚举。"
            f"(DifficultyLevel: Failed to decode JSON from '{index_json_path}': {e}. Cannot create dynamic DifficultyLevel enum.)"
        )
        return []
    except IOError as e:
        _enums_module_logger.error(
            f"DifficultyLevel: 读取 '{index_json_path}' 时发生IOError: {e}。无法创建动态 DifficultyLevel 枚举。"
            f"(DifficultyLevel: IOError occurred while reading '{index_json_path}': {e}. Cannot create dynamic DifficultyLevel enum.)"
        )
        return []
    except Exception as e:  # 捕获其他意外错误 (Catch other unexpected errors)
        _enums_module_logger.error(
            f"DifficultyLevel: 为创建枚举读取 '{index_json_path}' 时发生未知错误: {e}",
            exc_info=True,  # 记录完整的异常信息 (Log full exception information)
        )
        return []

# 执行函数以获取难度ID (Execute function to get difficulty IDs)
_difficulty_member_ids = _get_difficulty_ids_from_index_json()

# 根据获取的ID动态创建DifficultyLevel枚举 (Dynamically create DifficultyLevel enum based on fetched IDs)
if not _difficulty_member_ids:
    # 如果未能加载任何难度级别，记录严重错误并使用一个回退的枚举
    # (If failed to load any difficulty levels, log critical error and use a fallback enum)
    _enums_module_logger.critical(
        "严重错误：无法从 library/index.json 加载任何难度级别。"
        "应用功能将受到严重影响。"
        "正在使用包含单个 'unknown_difficulty' 成员的回退 DifficultyLevel。"
        "(CRITICAL ERROR: Cannot load any difficulty levels from library/index.json. "
        "Application functionality will be severely affected. "
        "Using a fallback DifficultyLevel with a single 'unknown_difficulty' member.)"
    )
    DifficultyLevel = Enum(
        "DifficultyLevel", {"unknown_difficulty": "unknown_difficulty"}, type=str
    )
else:
    # 使用获取到的ID创建枚举成员 (Use fetched IDs to create enum members)
    enum_members_map = {id_val: id_val for id_val in _difficulty_member_ids}
    DifficultyLevel = Enum("DifficultyLevel", enum_members_map, type=str)
    _enums_module_logger.info(
        f"成功动态创建 DifficultyLevel 枚举，成员 (Successfully dynamically created DifficultyLevel enum, members): {list(DifficultyLevel.__members__.keys())}"
    )
# endregion


class LogLevelEnum(str, Enum):
    """
    日志级别枚举。
    (Log Level Enumeration.)
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class PaperPassStatusEnum(str, Enum):
    """
    试卷通过状态枚举。
    (Paper Pass Status Enumeration.)

    - `PASSED`: 已通过考试。
    - `FAILED`: 未通过考试。
    - `GRADING`: （自动）批改中或客观题部分已批改。
    - `PENDING`: 试卷已创建但用户尚未提交，或处于其他待处理状态。
    - `PENDING_REVIEW`: 试卷已提交，客观题已自动批改，但包含主观题等待人工批阅。
    (
    - `PASSED`: Passed the exam.
    - `FAILED`: Failed the exam.
    - `GRADING`: (Auto)grading in progress, or objective part graded.
    - `PENDING`: Paper created but not yet submitted by user, or other pending states.
    - `PENDING_REVIEW`: Paper submitted, objective questions auto-graded, but contains subjective questions awaiting manual review.
    )
    """

    PASSED = "PASSED"  # 已通过 (Passed)
    FAILED = "FAILED"  # 未通过 (Failed)
    GRADING = (
        "GRADING"  # 批改中 (Grading in progress - if async/manual grading is needed)
    )
    PENDING = "PENDING"  # 待提交或待批改 (Pending submission or grading)
    PENDING_REVIEW = "PENDING_REVIEW"  # 客观题已批改，主观题待阅 (Objective part graded, subjective pending review)
    # 可以根据需要添加更多状态，例如 CANCELED, ERROR_IN_GRADING 等
    # (More statuses like CANCELED, ERROR_IN_GRADING can be added as needed)


class QuestionTypeEnum(str, Enum):
    """
    题目类型枚举。
    (Question Type Enumeration.)

    定义了系统中支持的各种题目类型：
    - `single_choice`: 单选题，用户从多个选项中选择一个正确答案。
    - `multiple_choice`: 多选题，用户从多个选项中选择一个或多个正确答案 (未来支持)。
    - `fill_in_blank`: 填空题，用户需要填写一个或多个空白处的答案 (未来支持)。
    - `essay_question`: 问答题/论述题，用户需要提供文本形式的详细答案，通常需要人工批阅。
    (Defines various question types supported in the system:
     - `single_choice`: Single choice, user selects one correct answer from multiple options.
     - `multiple_choice`: Multiple choice, user selects one or more correct answers (future support).
     - `fill_in_blank`: Fill-in-the-blank, user provides answers for one or more blanks (future support).
     - `essay_question`: Essay/subjective question, user provides detailed textual answer, usually requires manual grading.)
    """

    SINGLE_CHOICE = "single_choice"  # 单选题 (Single Choice)
    MULTIPLE_CHOICE = "multiple_choice"  # 多选题 (Multiple Choice - future support)
    FILL_IN_BLANK = "fill_in_blank"  # 填空题 (Fill-in-the-blank - future support)
    ESSAY_QUESTION = "essay_question"  # 问答题 (Essay Question - future support)


class AuthStatusCodeEnum(str, Enum):
    """
    认证相关的API状态码枚举。
    (API Status Code Enumeration for Authentication.)
    """

    # 成功类 (Success Types)
    AUTH_SUCCESS = "AUTH_SUCCESS"  # 通用认证成功 (General authentication success)
    # 客户端错误类 (Client Error Types)
    AUTH_WRONG_CREDENTIALS = (
        "AUTH_WRONG_CREDENTIALS"  # 用户名或密码错误 (Incorrect username or password)
    )
    AUTH_DUPLICATE_UID = "AUTH_DUPLICATE_UID"  # 用户名已存在 (Username already exists)
    AUTH_TOKEN_INVALID = (
        "AUTH_TOKEN_INVALID"  # Token无效或过期 (Token is invalid or expired)
    )
    AUTH_INACTIVE_USER = (
        "AUTH_INACTIVE_USER"  # 用户账户未激活或被封禁 (User account inactive or banned)
    )
    # 服务端错误可以不在此处定义，通常直接用HTTP 5xx
    # (Server errors usually use HTTP 5xx and might not be defined here)


__all__ = [
    "LogLevelEnum",
    "PaperPassStatusEnum",
    "QuestionTypeEnum",
    "AuthStatusCodeEnum",
    "DifficultyLevel", # ADDED
]

if __name__ == "__main__":
    print(f"此模块 ({__name__}) 定义了共享枚举类型，不应直接执行。")
    print(
        f"(This module ({__name__}) defines shared enumeration types and should not be executed directly.)"
    )
