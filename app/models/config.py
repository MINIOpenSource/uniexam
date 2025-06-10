# -*- coding: utf-8 -*-
"""
应用配置相关的Pydantic模型模块。
(Pydantic Models Module for Application Configuration.)

此模块定义了用于API请求体和响应体的Pydantic模型，
主要与应用的配置设置（settings.json）相关。
这些模型确保了通过API更新或获取配置信息时的数据结构的正确性和一致性。
(This module defines Pydantic models for API request and response bodies,
primarily related to the application's configuration settings (settings.json).
These models ensure the correctness and consistency of data structures when
updating or fetching configuration information via API.)
"""

# region 模块导入 (Module Imports)
from typing import Dict, Optional

from pydantic import BaseModel, Field

from .enums import LogLevelEnum  # 导入新的枚举 (Import the new enum)

# endregion

# region 配置子结构载荷模型 (Payload Models for Configuration Sub-structures)
# 这些模型用于在 SettingsUpdatePayload 和 SettingsResponseModel 中表示可配置的子部分。
# (These models are used within SettingsUpdatePayload and SettingsResponseModel
#  to represent configurable sub-sections.)


class RateLimitConfigPayload(BaseModel):
    """
    速率限制配置的载荷/响应模型。
    (Payload/Response model for rate limit configuration.)
    """

    limit: Optional[int] = Field(
        None, description="在时间窗口内的最大请求次数 (Max requests in time window)"
    )
    window: Optional[int] = Field(
        None, description="时间窗口大小（秒）(Time window size in seconds)"
    )


class UserTypeRateLimitsPayload(BaseModel):
    """
    特定用户类型的速率限制配置集合的载荷/响应模型。
    (Payload/Response model for rate limit configurations of a specific user type.)
    """

    get_exam: Optional[RateLimitConfigPayload] = Field(
        None, description="获取新试卷接口的速率限制 (Rate limit for get_exam endpoint)"
    )
    auth_attempts: Optional[RateLimitConfigPayload] = Field(
        None,
        description="认证尝试（登录/注册）的速率限制 (Rate limit for auth attempts)",
    )


class CloudflareIPsConfigPayload(BaseModel):
    """
    Cloudflare IP范围获取配置的载荷/响应模型。
    (Payload/Response model for Cloudflare IP range fetching configuration.)
    """

    v4_url: Optional[str] = Field(
        None, description="Cloudflare IPv4地址范围列表URL (Cloudflare IPv4 list URL)"
    )
    v6_url: Optional[str] = Field(
        None, description="Cloudflare IPv6地址范围列表URL (Cloudflare IPv6 list URL)"
    )
    fetch_interval_seconds: Optional[int] = Field(
        None,
        description="自动更新Cloudflare IP范围的时间间隔（秒）(Auto-update interval in seconds)",
    )


class DatabaseFilesConfigPayload(BaseModel):
    """
    JSON数据库文件路径配置的载荷/响应模型。
    (Payload/Response model for JSON database file path configuration.)
    """

    papers: Optional[str] = Field(
        None, description="存储试卷数据的文件名 (Filename for paper data)"
    )
    users: Optional[str] = Field(
        None, description="存储用户数据的文件名 (Filename for user data)"
    )


class UserValidationConfigPayload(BaseModel):
    """
    用户注册验证规则配置的载荷/响应模型。
    (Payload/Response model for user registration validation rule configuration.)
    """

    uid_min_len: Optional[int] = Field(
        None, description="用户名最小长度 (Min username length)"
    )
    uid_max_len: Optional[int] = Field(
        None, description="用户名最大长度 (Max username length)"
    )
    password_min_len: Optional[int] = Field(
        None, description="密码最小长度 (Min password length)"
    )
    password_max_len: Optional[int] = Field(
        None, description="密码最大长度 (Max password length)"
    )
    uid_regex: Optional[str] = Field(
        None, description="用户名的正则表达式 (Username regex)"
    )


# endregion


class SettingsResponseModel(BaseModel):
    """
    用于API响应中表示应用配置（例如管理员获取配置）的Pydantic模型。
    字段均为可选，以反映 `settings.json` 文件可能不包含所有键的实际状态。
    此模型主要用于展示可以被管理员查看或修改的配置项。
    (Pydantic model for representing application configuration in API responses
    (e.g., when an admin fetches settings). Fields are optional to reflect that
    `settings.json` may not contain all keys. This model primarily shows
    configurable items viewable or modifiable by an admin.)
    """

    app_name: Optional[str] = Field(None, description="应用名称 (Application name)")
    token_expiry_hours: Optional[int] = Field(
        None, description="Token过期小时数 (Token expiry in hours)"
    )
    token_length_bytes: Optional[int] = Field(
        None, description="Token字节长度 (Token byte length)"
    )
    num_questions_per_paper_default: Optional[int] = Field(
        None, description="默认每份试卷题目数 (Default questions per paper)"
    )
    num_correct_choices_to_select: Optional[int] = Field(
        None, description="选择题正确选项选取数 (Number of correct choices to select)"
    )
    num_incorrect_choices_to_select: Optional[int] = Field(
        None, description="选择题错误选项选取数 (Number of incorrect choices to select)"
    )
    generated_code_length_bytes: Optional[int] = Field(
        None, description="随机码字节长度 (Random code byte length)"
    )
    passing_score_percentage: Optional[float] = Field(
        None, description="及格分数百分比 (Passing score percentage)"
    )
    db_persist_interval_seconds: Optional[int] = Field(
        None, description="数据库持久化间隔秒数 (DB persistence interval in seconds)"
    )
    rate_limits: Optional[Dict[str, UserTypeRateLimitsPayload]] = Field(
        None, description="速率限制配置 (Rate limit configurations)"
    )
    cloudflare_ips: Optional[CloudflareIPsConfigPayload] = Field(
        None, description="Cloudflare IP获取配置 (Cloudflare IP fetching config)"
    )
    log_file_name: Optional[str] = Field(None, description="日志文件名 (Log filename)")
    log_level: Optional[LogLevelEnum] = Field(  # 使用枚举类型 (Use the enum type)
        None, description="应用日志级别 (Application log level)"
    )
    database_files: Optional[DatabaseFilesConfigPayload] = Field(
        None, description="JSON数据库文件名配置 (JSON database filename config)"
    )
    question_library_path: Optional[str] = Field(
        None, description="题库文件夹路径 (Question library folder path)"
    )
    question_library_index_file: Optional[str] = Field(
        None, description="题库索引文件名 (Question library index filename)"
    )
    user_config: Optional[UserValidationConfigPayload] = Field(
        None, description="用户验证规则配置 (User validation rule config)"
    )
    enable_uvicorn_access_log: Optional[bool] = Field(
        None, description="是否启用Uvicorn访问日志 (Enable Uvicorn access log)"
    )  # 新增
    debug_mode: Optional[bool] = Field(
        None,
        description="是否启用调试模式 (主要用于uvicorn重载) (Enable debug mode (mainly for uvicorn reload))",
    )  # 新增

    model_config = {
        "extra": "ignore"
    }  # 忽略从 settings.json 读取时可能存在的多余字段 (Ignore extra fields from settings.json)


class SettingsUpdatePayload(BaseModel):
    """
    管理员更新应用配置时使用的Pydantic请求体模型。
    所有字段均为可选，允许管理员只更新部分配置项。
    (Pydantic request body model used when an admin updates application configuration.
    All fields are optional, allowing admins to update only a subset of config items.)
    """

    app_name: Optional[str] = Field(None, description="应用名称 (Application name)")
    token_expiry_hours: Optional[int] = Field(
        None,
        ge=1,
        description="Token过期小时数 (必须大于等于1) (Token expiry in hours (must be >= 1))",
    )
    token_length_bytes: Optional[int] = Field(
        None, ge=16, le=64, description="Token字节长度 (Token byte length)"
    )
    num_questions_per_paper_default: Optional[int] = Field(
        None, ge=1, description="默认每份试卷题目数 (Default questions per paper)"
    )
    num_correct_choices_to_select: Optional[int] = Field(
        None,
        ge=1,
        description="选择题正确选项选取数 (Number of correct choices to select)",
    )
    num_incorrect_choices_to_select: Optional[int] = Field(
        None,
        ge=1,
        description="选择题错误选项选取数 (Number of incorrect choices to select)",
    )
    generated_code_length_bytes: Optional[int] = Field(
        None, ge=4, le=16, description="随机码字节长度 (Random code byte length)"
    )
    passing_score_percentage: Optional[float] = Field(
        None, ge=0, le=100, description="及格分数百分比 (Passing score percentage)"
    )
    db_persist_interval_seconds: Optional[int] = Field(
        None,
        ge=10,
        description="数据库持久化间隔秒数 (DB persistence interval in seconds)",
    )
    rate_limits: Optional[Dict[str, UserTypeRateLimitsPayload]] = Field(
        None, description="速率限制配置 (Rate limit configurations)"
    )
    cloudflare_ips: Optional[CloudflareIPsConfigPayload] = Field(
        None, description="Cloudflare IP获取配置 (Cloudflare IP fetching config)"
    )
    log_file_name: Optional[str] = Field(None, description="日志文件名 (Log filename)")
    log_level: Optional[LogLevelEnum] = Field(  # 使用枚举类型 (Use the enum type)
        None,
        description="应用日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL) (Application log level)",
    )
    database_files: Optional[DatabaseFilesConfigPayload] = Field(
        None, description="数据库文件路径配置 (Database file path config)"
    )
    question_library_path: Optional[str] = Field(
        None,
        description="题库文件夹路径 (相对于data目录) (Question library folder path (relative to data dir))",
    )
    question_library_index_file: Optional[str] = Field(
        None, description="题库索引文件名 (Question library index filename)"
    )
    user_config: Optional[UserValidationConfigPayload] = Field(
        None, description="用户验证规则配置 (User validation rule config)"
    )
    enable_uvicorn_access_log: Optional[bool] = Field(
        None, description="是否启用Uvicorn访问日志 (Enable Uvicorn access log)"
    )  # 新增
    debug_mode: Optional[bool] = Field(
        None, description="是否启用调试模式 (Enable debug mode)"
    )  # 新增

    model_config = {
        "extra": "forbid"
    }  # 更新时禁止未知字段 (Forbid unknown fields on update)


__all__ = [
    "RateLimitConfigPayload",
    "UserTypeRateLimitsPayload",
    "CloudflareIPsConfigPayload",
    "DatabaseFilesConfigPayload",
    "UserValidationConfigPayload",
    "SettingsResponseModel",
    "SettingsUpdatePayload",
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了与应用配置相关的Pydantic模型。
    # (This module should not be executed as the main script. It defines Pydantic models
    #  related to application configuration.)
    print(f"此模块 ({__name__}) 定义了与应用配置相关的Pydantic模型，不应直接执行。")
    print(
        f"(This module ({__name__}) defines Pydantic models related to application configuration and should not be executed directly.)"
    )
