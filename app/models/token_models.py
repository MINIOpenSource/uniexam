# -*- coding: utf-8 -*-
"""
Token及认证状态相关的Pydantic模型模块。
(Pydantic Models Module for Tokens and Authentication Status.)

此模块定义了用于API认证流程的数据结构，例如：
- `Token`: API成功登录或刷新Token后返回的标准响应体。
- `TokenData`: Token在内部存储或解析后所承载的数据结构。
- `AuthStatusResponse`: 用于表示认证失败或特定认证状态的通用响应模型。

(This module defines data structures used in the API authentication process, such as:
- `Token`: Standard response body returned after successful login or token refresh.
- `TokenData`: Data structure حملed by a token when stored internally or after parsing.
- `AuthStatusResponse`: Generic response model for representing authentication failures
  or specific authentication statuses.)
"""

# region 模块导入 (Module Imports)
from typing import List, Optional

from pydantic import BaseModel, Field

from .enums import AuthStatusCodeEnum  # 导入认证状态码枚举
from .user_models import UserTag  # 导入用户标签枚举 (Import UserTag enum)

# endregion


# region Token模型 (Token Model)
class Token(BaseModel):
    """
    API Token模型，用于登录和刷新Token成功时的标准响应体。
    符合OAuth 2.0 Bearer Token响应的常见结构。
    (API Token model, used as the standard response body for successful login and token refresh.
    Conforms to the common structure of an OAuth 2.0 Bearer Token response.)
    """

    access_token: str = Field(
        description="访问令牌 (通常是一个随机生成的长字符串)。(Access token (usually a long, randomly generated string).)"
    )
    token_type: str = Field(
        default="bearer",
        description="令牌类型，固定为 'bearer'。(Token type, fixed as 'bearer'.)",
    )
    # 可以添加 expires_in (秒) 或 user_info 等字段
    # (Can add fields like expires_in (seconds) or user_info, etc.)
    # user_info: Optional[UserPublicProfile] = None # 例如，登录成功时一并返回用户信息 (e.g., return user info upon successful login)


# endregion


# region Token数据模型 (TokenData Model)
class TokenData(BaseModel):
    """
    Token内部存储或解析后承载的数据模型。
    如果使用JWT，这可以代表JWT的载荷 (payload) 部分。
    对于当前基于内存字典的简单Token方案，这是存储在 `_active_tokens` 中的值结构。
    (Data model carried by a token when stored internally or after parsing.
    If using JWT, this can represent the payload part of the JWT.
    For the current simple token scheme based on an in-memory dictionary, this is
    the structure of the value stored in `_active_tokens`.)
    """

    user_uid: str = Field(
        description="关联的用户唯一标识符 (uid)。(Associated user's unique identifier (uid).)"
    )
    tags: List[UserTag] = Field(
        default_factory=list,
        description="用户拥有的标签列表，用于权限控制。(List of tags possessed by the user, for permission control.)",
    )
    expires_at: float = Field(
        description="Token的过期时间戳 (time.time()的浮点数表示)。(Token's expiration timestamp (float representation of time.time()).)"
    )
    # 可以添加其他需要在Token中快速访问的信息，如签发时间 (iat) 等
    # (Can add other information needed for quick access in the token, such as issued-at time (iat), etc.)


# endregion


# region Auth Status Response Model (认证状态响应模型)
class AuthStatusResponse(BaseModel):
    """
    用于认证失败或特定状态响应的通用模型。
    (Generic model for authentication failure or specific status responses.)
    """

    status_code: AuthStatusCodeEnum = Field(  # 使用枚举类型 (Use enum type)
        description="表示认证结果或特定状态的代码。(Code representing authentication result or specific status.)"
    )
    message: Optional[str] = Field(
        None, description="相关的消息文本 (可选)。(Related message text (optional).)"
    )


# endregion

__all__ = [
    "Token",
    "TokenData",
    "AuthStatusResponse",
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了与Token和认证状态相关的Pydantic模型。
    # (This module should not be executed as the main script. It defines Pydantic models
    #  related to tokens and authentication status.)
    print(
        f"此模块 ({__name__}) 定义了与Token和认证状态相关的Pydantic模型，不应直接执行。"
    )
    print(
        f"(This module ({__name__}) defines Pydantic models related to tokens and authentication status and should not be executed directly.)"
    )
