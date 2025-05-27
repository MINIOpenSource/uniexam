# -*- coding: utf-8 -*-
# region 模块导入
from typing import Optional, Dict, List
from pydantic import BaseModel, Field

# Import sub-models from app.core.config to be used here
# We need to be careful with direct imports from app.core.config.Settings
# to avoid circular dependencies if Settings itself imports from models.
# For now, we'll redefine the necessary sub-structures or assume they are simple enough.
# A better approach might be to have base config models in a neutral place.

# Re-defining sub-models for clarity and to avoid direct dependency on Settings sub-models if complex
class RateLimitConfigPayload(BaseModel):
    limit: Optional[int] = None
    window: Optional[int] = None

class UserTypeRateLimitsPayload(BaseModel):
    get_exam: Optional[RateLimitConfigPayload] = None
    auth_attempts: Optional[RateLimitConfigPayload] = None

class CloudflareIPsConfigPayload(BaseModel):
    v4_url: Optional[str] = None
    v6_url: Optional[str] = None
    fetch_interval_seconds: Optional[int] = None

class DatabaseFilesConfigPayload(BaseModel):
    papers: Optional[str] = None
    users: Optional[str] = None

class UserValidationConfigPayload(BaseModel):
    uid_min_len: Optional[int] = None
    uid_max_len: Optional[int] = None
    password_min_len: Optional[int] = None
    password_max_len: Optional[int] = None
    uid_regex: Optional[str] = None

# endregion

class SettingsResponseModel(BaseModel):
    """
    Pydantic model for representing application settings in API responses (e.g., for admin).
    Fields are optional as they reflect the state of settings.json which might not have all keys.
    """
    app_name: Optional[str] = None
    # app_domain, frontend_domain, listening_port are usually from .env, not settings.json for update
    token_expiry_hours: Optional[int] = None
    token_length_bytes: Optional[int] = None
    num_questions_per_paper_default: Optional[int] = None
    num_correct_choices_to_select: Optional[int] = None
    num_incorrect_choices_to_select: Optional[int] = None
    generated_code_length_bytes: Optional[int] = None
    passing_score_percentage: Optional[float] = None
    db_persist_interval_seconds: Optional[int] = None
    rate_limits: Optional[Dict[str, UserTypeRateLimitsPayload]] = None
    cloudflare_ips: Optional[CloudflareIPsConfigPayload] = None
    log_file_name: Optional[str] = None
    log_level: Optional[str] = None # 新增日志级别
    database_files: Optional[DatabaseFilesConfigPayload] = None
    question_library_path: Optional[str] = None
    question_library_index_file: Optional[str] = None
    user_config: Optional[UserValidationConfigPayload] = None

    model_config = {
        "extra": "ignore" # Ignore extra fields from settings.json if any
    }

class SettingsUpdatePayload(BaseModel):
    """
    Pydantic model for the payload when an admin updates application settings.
    All fields are optional, allowing partial updates.
    """
    app_name: Optional[str] = Field(None, description="应用名称")
    token_expiry_hours: Optional[int] = Field(None, ge=1, description="Token过期小时数")
    token_length_bytes: Optional[int] = Field(None, ge=16, le=64, description="Token字节长度")
    
    num_questions_per_paper_default: Optional[int] = Field(None, ge=1, description="默认每份试卷题目数")
    num_correct_choices_to_select: Optional[int] = Field(None, ge=1, description="选择题正确选项选取数")
    num_incorrect_choices_to_select: Optional[int] = Field(None, ge=1, description="选择题错误选项选取数")
    generated_code_length_bytes: Optional[int] = Field(None, ge=4, le=16, description="随机码字节长度")

    passing_score_percentage: Optional[float] = Field(None, ge=0, le=100, description="及格分数百分比")
    db_persist_interval_seconds: Optional[int] = Field(None, ge=10, description="数据库持久化间隔秒数")
    
    rate_limits: Optional[Dict[str, UserTypeRateLimitsPayload]] = Field(None, description="速率限制配置")
    cloudflare_ips: Optional[CloudflareIPsConfigPayload] = Field(None, description="Cloudflare IP获取配置")
    log_file_name: Optional[str] = Field(None, description="日志文件名")
    log_level: Optional[str] = Field(None, description="应用日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)") # 新增
    database_files: Optional[DatabaseFilesConfigPayload] = Field(None, description="数据库文件路径配置")
    
    question_library_path: Optional[str] = Field(None, description="题库文件夹路径 (相对于data目录)")
    question_library_index_file: Optional[str] = Field(None, description="题库索引文件名")
    
    user_config: Optional[UserValidationConfigPayload] = Field(None, description="用户验证规则配置")

    # Fields typically set by .env and not via API, so excluded from update payload:
    # app_domain, frontend_domain, listening_port, default_admin_password_override

    model_config = {
        "extra": "forbid" # Forbid extra fields in update payload
    }