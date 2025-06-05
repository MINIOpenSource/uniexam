# -*- coding: utf-8 -*-
"""
共享枚举类型模块。
(Shared Enumeration Types Module.)

此模块定义了在整个应用中可能被多个模块复用的枚举类型。
(This module defines enumeration types that may be reused by multiple modules
across the application.)
"""
from enum import Enum


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
    """

    PASSED = "PASSED"  # 已通过 (Passed)
    FAILED = "FAILED"  # 未通过 (Failed)
    GRADING = (
        "GRADING"  # 批改中 (Grading in progress - if async/manual grading is needed)
    )
    PENDING = "PENDING"  # 待提交或待批改 (Pending submission or grading)
    # 可以根据需要添加更多状态，例如 CANCELED, ERROR_IN_GRADING 等
    # (More statuses like CANCELED, ERROR_IN_GRADING can be added as needed)


class QuestionTypeEnum(str, Enum):
    """
    题目类型枚举。
    (Question Type Enumeration.)
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
]

if __name__ == "__main__":
    print(f"此模块 ({__name__}) 定义了共享枚举类型，不应直接执行。")
    print(
        f"(This module ({__name__}) defines shared enumeration types and should not be executed directly.)"
    )
