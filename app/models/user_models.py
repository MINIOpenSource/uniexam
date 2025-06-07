# -*- coding: utf-8 -*-
"""
用户相关的Pydantic模型模块。
(Pydantic Models Module for User-related Data.)

此模块定义了用于处理用户账户、认证、个人资料以及管理员操作所需的数据结构。
这些模型广泛应用于API的请求体、响应体、数据库存储以及内部数据传递。
(This module defines data structures required for handling user accounts,
authentication, profiles, and administrative operations. These models are
extensively used in API request/response bodies, database storage, and
for internal data transfer.)
"""

# region 模块导入 (Module Imports)
import re  # 用于正则表达式验证 (For regular expression validation)
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from ..core.config import settings  # 导入全局配置 (Import global settings)

# endregion


# region 用户标签枚举 (UserTag Enum)
class UserTag(str, Enum):
    """
    用户标签枚举，定义了不同用户角色的权限级别。
    (User tag enum, defining permission levels for different user roles.)
    """

    ADMIN = "admin"  # 管理员：最高权限 (Admin: Highest privileges)
    USER = "user"  # 普通用户 (Regular user)
    BANNED = "banned"  # 禁用用户 (Banned user)
    LIMITED = "limited"  # 受限用户 (Limited user with stricter rate limits)
    GRADER = "grader"  # 批阅者 (Grader for subjective questions)
    EXAMINER = "examiner"  # 出题者/题库管理员 (Question creator/bank admin)
    MANAGER = "manager"  # 运营管理员 (Operational manager)

    @classmethod
    def get_default_tags(cls) -> List["UserTag"]:
        """获取新注册用户的默认标签列表。(Gets the default list of tags for new users.)"""
        return [cls.USER]


# endregion


# region 用户基础模型 (UserBase Model)
class UserBase(BaseModel):
    """
    用户基础信息模型，API请求体和其它用户模型的基类。
    (Base model for user information, used in API request bodies and as a base for other user models.)
    """

    uid: str = Field(
        ...,
        min_length=settings.user_config.uid_min_len,
        max_length=settings.user_config.uid_max_len,
        description=f"用户名 ({settings.user_config.uid_min_len}-{settings.user_config.uid_max_len}位，只能是小写字母、数字或下划线)。(Username ({settings.user_config.uid_min_len}-{settings.user_config.uid_max_len} chars, lowercase letters, numbers, or underscores only).)",
    )
    nickname: Optional[str] = Field(
        None,
        max_length=50,
        description="用户昵称 (可选, 最长50个字符)。(User nickname (optional, max 50 chars).)",
    )
    email: Optional[EmailStr] = Field(
        None,
        description="电子邮箱 (可选, 必须是有效的邮箱格式)。(Email (optional, must be a valid email format).)",
    )
    qq: Optional[str] = Field(
        None,
        max_length=15,
        pattern=r"^[1-9][0-9]{4,14}$",
        description="QQ号码 (可选, 5-15位数字)。(QQ number (optional, 5-15 digits).)",
    )

    @field_validator("uid")
    @classmethod
    def uid_must_match_regex_and_length(
        cls, value: str
    ) -> str:  # Renamed validator for clarity
        """
        验证UID是否符合配置中定义的正则表达式和长度。
        (Validates if UID conforms to the regex and length defined in settings.)
        """
        uid_config = settings.user_config
        if not (uid_config.uid_min_len <= len(value) <= uid_config.uid_max_len):
            raise ValueError(
                f"用户名的长度必须在 {uid_config.uid_min_len} 和 {uid_config.uid_max_len} 之间。(Username length must be between {uid_config.uid_min_len} and {uid_config.uid_max_len}.)"
            )
        if not re.match(uid_config.uid_regex, value):
            raise ValueError(
                "用户名只能包含小写字母、数字或下划线。(Username can only contain lowercase letters, numbers, or underscores.)"
            )
        return value


# endregion


# region 用户创建模型 (UserCreate Model)
class UserCreate(UserBase):
    """
    用户注册时使用的模型，继承自UserBase并添加了密码字段。
    (Model used for user registration, inherits from UserBase and adds a password field.)
    """

    password: str = Field(
        ...,
        min_length=settings.user_config.password_min_len,
        max_length=settings.user_config.password_max_len,
        description=f"密码 ({settings.user_config.password_min_len}-{settings.user_config.password_max_len} 位)。(Password ({settings.user_config.password_min_len}-{settings.user_config.password_max_len} chars).)",
    )


# endregion


# region 用户个人资料更新模型 (UserProfileUpdate Model)
class UserProfileUpdate(BaseModel):
    """
    用户更新个人资料时使用的模型，所有字段都是可选的。
    (Model used when a user updates their profile, all fields are optional.)
    """

    nickname: Optional[str] = Field(
        None,
        max_length=50,
        description="新的用户昵称 (可选)。(New user nickname (optional).)",
    )
    email: Optional[EmailStr] = Field(
        None, description="新的电子邮箱 (可选)。(New email (optional).)"
    )
    qq: Optional[str] = Field(
        None,
        max_length=15,
        pattern=r"^[1-9][0-9]{4,14}$",
        description="新的QQ号码 (可选)。(New QQ number (optional).)",
    )


# endregion


# region 用户密码更新模型 (UserPasswordUpdate Model)
class UserPasswordUpdate(BaseModel):
    """
    用户更新密码时使用的模型。
    (Model used when a user updates their password.)
    """

    current_password: str = Field(..., description="当前密码。(Current password.)")
    new_password: str = Field(
        ...,
        min_length=settings.user_config.password_min_len,
        max_length=settings.user_config.password_max_len,
        description=f"新密码 ({settings.user_config.password_min_len}-{settings.user_config.password_max_len} 位)。(New password ({settings.user_config.password_min_len}-{settings.user_config.password_max_len} chars).)",
    )


# endregion


# region 数据库中存储的用户模型 (UserInDBBase and UserInDB Models)
class UserInDBBase(UserBase):
    """
    数据库中存储的用户基础模型，在UserBase基础上添加了标签。
    (Base model for users stored in the database, adds tags to UserBase.)
    """

    tags: List[UserTag] = Field(
        default_factory=UserTag.get_default_tags,
        description="用户标签列表，决定用户权限和行为。(List of user tags, determining permissions and behavior.)",
    )
    model_config = {"from_attributes": True}  # Pydantic v2 orm_mode equivalent


class UserInDB(UserInDBBase):
    """
    数据库中存储的完整用户模型，继承自UserInDBBase并添加了哈希后的密码。
    (Complete model for users stored in the database, inherits from UserInDBBase and adds hashed password.)
    """

    hashed_password: str = Field(
        ..., description="哈希后的用户密码。(Hashed user password.)"
    )


# endregion


# region 用于API响应的用户信息模型 (UserPublicProfile Model)
class UserPublicProfile(UserBase):
    """
    作为API响应返回给客户端的用户公开信息模型。不包含密码等敏感信息。
    (Public user information model returned to clients in API responses. Excludes sensitive info like passwords.)
    """

    tags: List[UserTag] = Field(description="用户标签列表。(List of user tags.)")
    model_config = {"from_attributes": True}


# endregion


# region Admin 编辑用户时使用的模型 (AdminUserUpdate Model)
class AdminUserUpdate(BaseModel):
    """
    管理员编辑用户信息时使用的模型。允许修改更多字段。
    (Model used when an admin edits user information. Allows modification of more fields.)
    """

    nickname: Optional[str] = Field(
        None,
        max_length=50,
        description="新的用户昵称 (可选)。(New user nickname (optional).)",
    )
    email: Optional[EmailStr] = Field(
        None, description="新的电子邮箱 (可选)。(New email (optional).)"
    )
    qq: Optional[str] = Field(
        None,
        max_length=15,
        pattern=r"^[1-9][0-9]{4,14}$",
        description="新的QQ号码 (可选)。(New QQ number (optional).)",
    )
    tags: Optional[List[UserTag]] = Field(
        None,
        description="新的用户标签列表 (可选, 如果提供则完全替换旧标签)。(New list of user tags (optional, replaces old tags if provided).)",
    )
    new_password: Optional[str] = Field(
        None,
        min_length=settings.user_config.password_min_len,
        max_length=settings.user_config.password_max_len,
        description=f"(可选) 为用户设置新密码 ({settings.user_config.password_min_len}-{settings.user_config.password_max_len} 位)。如果提供，将覆盖用户现有密码。((Optional) Set a new password for the user ({settings.user_config.password_min_len}-{settings.user_config.password_max_len} chars). Overwrites existing password if provided.)",
    )


# endregion


# region 用户目录条目模型 (UserDirectoryEntry Model)
class UserDirectoryEntry(BaseModel):
    """
    用于在公共名录中列出具有特殊角色的用户的模型。
    (Model for listing users with special roles in a public directory.)
    """

    uid: str = Field(description="用户ID (用户名)。(User ID (username).)")
    nickname: Optional[str] = Field(
        None, description="用户昵称 (如果可用)。(User nickname (if available).)"
    )
    tags: List[UserTag] = Field(
        description="用户标签，指示其角色/类别。(User tags indicating their roles/categories.)"
    )


# endregion

__all__ = [
    "UserTag",
    "UserBase",
    "UserCreate",
    "UserProfileUpdate",
    "UserPasswordUpdate",
    "UserInDBBase",
    "UserInDB",
    "UserPublicProfile",
    "AdminUserUpdate",
    "UserDirectoryEntry",
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了与用户相关的Pydantic模型。
    # (This module should not be executed as the main script. It defines Pydantic models
    #  related to users.)
    print(f"此模块 ({__name__}) 定义了与用户相关的Pydantic模型，不应直接执行。")
    print(
        f"(This module ({__name__}) defines Pydantic models related to users and should not be executed directly.)"
    )
