# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field

class UserValidationConfig(BaseModel):
    """
    用户注册时的验证规则配置模型。
    定义了用户名和密码的长度及格式要求。
    (Validation rule configuration model for user registration.
    Defines length and format requirements for username and password.)
    """
    uid_min_len: int = Field(
        5, ge=1, description="用户名最小长度 (Min username length)"
    )
    uid_max_len: int = Field(16, description="用户名最大长度 (Max username length)")
    password_min_len: int = Field(
        8, ge=1, description="密码最小长度 (Min password length)"
    )
    password_max_len: int = Field(48, description="密码最大长度 (Max password length)")
    uid_regex: str = Field(
        r"^[a-z0-9_]+$",
        description="用户名的正则表达式，限制为小写字母、数字和下划线 (Regex for username: lowercase letters, numbers, underscore)",
    )

__all__ = ["UserValidationConfig"]
