# -*- coding: utf-8 -*-
# region 模块导入
from enum import Enum
from typing import List, Optional, Dict, Any # 确保导入了 Dict, Any
from pydantic import BaseModel, Field, EmailStr, validator, field_validator
import re # 用于正则表达式验证

# 使用相对导入从同级 core 包导入配置和枚举
# 假设 settings 从 app.core.config 导入，用于获取验证规则
from ..core.config import settings 
# endregion

# region 用户标签枚举 (UserTag)
class UserTag(str, Enum):
    """
    用户标签枚举，定义了不同用户角色的权限级别。
    这些标签用于权限控制和应用特定策略。
    """
    ADMIN = "admin"        # 管理员：最高权限，可访问后台，通常无速率限制
    USER = "user"          # 普通用户：应用标准用户策略
    BANNED = "banned"      # 禁用用户：所有请求被禁止（除特定解封接口外）
    LIMITED = "limited"    # 受限用户：应用更严格的速率限制策略
    GRADER = "grader"      # 批阅者：可批阅主观题
    EXAMINER = "examiner"  # 出题者/题库管理员：Grader权限 + 访问和修改题库
    MANAGER = "manager"    # 运营管理员：Examiner权限 + 试卷管理（例如删除、查看所有试卷）

    @classmethod
    def get_default_tags(cls) -> List['UserTag']:
        """获取新注册用户的默认标签列表。"""
        return [cls.USER]
# endregion

# region 用户基础模型 (UserBase)
class UserBase(BaseModel):
    """
    用户基础信息模型，用于API请求体和作为其他用户模型的基类。
    包含用户通用的、可公开或可编辑的个人信息字段。
    """
    uid: str = Field(
        ..., # 表示此字段是必需的
        min_length=settings.user_config.uid_min_len,
        max_length=settings.user_config.uid_max_len,
        # pattern=settings.user_config.uid_regex, # pattern已通过下面的validator实现
        description=(
            f"用户名 ({settings.user_config.uid_min_len}-"
            f"{settings.user_config.uid_max_len}位，"
            f"只能是小写字母、数字或下划线)"
        )
    )
    nickname: Optional[str] = Field(
        None, # 默认为None，表示可选
        max_length=50,
        description="用户昵称 (可选, 最长50个字符)"
    )
    email: Optional[EmailStr] = Field(
        None, # 默认为None，表示可选
        description="电子邮箱 (可选, 必须是有效的邮箱格式)"
    ) # Pydantic 会自动验证邮箱格式
    qq: Optional[str] = Field(
        None, # 默认为None，表示可选
        max_length=15,
        pattern=r"^[1-9][0-9]{4,14}$", # QQ号通常是5到15位数字，首位不为0
        description="QQ号码 (可选, 5-15位数字)"
    )

    # 使用 Pydantic v2 的 field_validator 来验证 uid 格式
    @field_validator('uid')
    @classmethod
    def uid_must_match_regex(cls, value: str) -> str:
        """验证UID是否符合配置中定义的正则表达式和长度。"""
        uid_config = settings.user_config
        if not (uid_config.uid_min_len <= len(value) <= uid_config.uid_max_len):
            raise ValueError(
                f"用户名的长度必须在 {uid_config.uid_min_len} 和 "
                f"{uid_config.uid_max_len} 之间。"
            )
        if not re.match(uid_config.uid_regex, value):
            raise ValueError("用户名只能包含小写字母、数字或下划线。")
        return value
# endregion

# region 用户创建模型 (UserCreate)
class UserCreate(UserBase):
    """用户注册时使用的模型，继承自UserBase并添加了密码字段。"""
    password: str = Field(
        ..., # 密码是必需的
        min_length=settings.user_config.password_min_len,
        max_length=settings.user_config.password_max_len,
        description=(
            f"密码 ({settings.user_config.password_min_len}-"
            f"{settings.user_config.password_max_len} 位)"
        )
    )
# endregion

# region 用户个人资料更新模型 (UserProfileUpdate)
class UserProfileUpdate(BaseModel):
    """用户更新个人资料时使用的模型，所有字段都是可选的。"""
    nickname: Optional[str] = Field(
        None,
        max_length=50,
        description="新的用户昵称 (可选)"
    )
    email: Optional[EmailStr] = Field(
        None,
        description="新的电子邮箱 (可选)"
    )
    qq: Optional[str] = Field(
        None,
        max_length=15,
        pattern=r"^[1-9][0-9]{4,14}$",
        description="新的QQ号码 (可选)"
    )

    # 可以添加一个模型验证器 (model_validator) 来确保至少提供了一个字段进行更新，
    # 但这通常在API路由处理函数中更容易检查（例如，检查请求体是否为空）。
    # @model_validator(mode='before') # Pydantic v2
    # def check_at_least_one_value(cls, data: Any) -> Any:
    #     if isinstance(data, dict) and not any(data.values()):
    #         raise ValueError("至少需要提供一个字段进行更新。")
    #     return data
# endregion

# region 用户密码更新模型 (UserPasswordUpdate)
class UserPasswordUpdate(BaseModel):
    """用户更新密码时使用的模型。"""
    current_password: str = Field(..., description="当前密码")
    new_password: str = Field(
        ...,
        min_length=settings.user_config.password_min_len,
        max_length=settings.user_config.password_max_len,
        description=(
            f"新密码 ({settings.user_config.password_min_len}-"
            f"{settings.user_config.password_max_len} 位)"
        )
    )
# endregion

# region 数据库中存储的用户模型 (UserInDBBase 和 UserInDB)
class UserInDBBase(UserBase):
    """
    数据库中存储的用户基础模型，在UserBase基础上添加了标签。
    这个模型主要用于类型提示和作为 UserInDB 的基类。
    """
    tags: List[UserTag] = Field(
        default_factory=UserTag.get_default_tags, # 新用户默认拥有 "user" 标签
        description="用户标签列表，决定用户权限和行为"
    )
    
    model_config = { # Pydantic v2 配置方式
        "from_attributes": True # 允许从ORM对象或其他属性对象创建模型实例 (旧称 orm_mode)
    }

class UserInDB(UserInDBBase):
    """
    数据库中存储的完整用户模型，继承自UserInDBBase并添加了哈希后的密码。
    这是实际存储在 users_db.json 中的用户对象结构。
    """
    hashed_password: str = Field(..., description="哈希后的用户密码")
# endregion

# region 用于API响应的用户信息模型 (UserPublicProfile)
class UserPublicProfile(UserBase):
    """
    作为API响应返回给客户端的用户公开信息模型。
    不包含密码等敏感信息。
    """
    tags: List[UserTag] = Field(description="用户标签列表")
    # 可以根据需要添加其他希望公开的字段，例如注册时间、最后登录时间等，
    # 这些字段需要先在 UserInDB 中定义和存储。
    
    model_config = {
        "from_attributes": True
    }
# endregion

# region Admin 编辑用户时使用的模型 (AdminUserUpdate)
class AdminUserUpdate(BaseModel):
    """管理员编辑用户信息时使用的模型。允许修改更多字段。"""
    nickname: Optional[str] = Field(
        None,
        max_length=50,
        description="新的用户昵称 (可选)"
    )
    email: Optional[EmailStr] = Field(
        None,
        description="新的电子邮箱 (可选)"
    )
    qq: Optional[str] = Field(
        None,
        max_length=15,
        pattern=r"^[1-9][0-9]{4,14}$",
        description="新的QQ号码 (可选)"
    )
    tags: Optional[List[UserTag]] = Field(
        None,
        description="新的用户标签列表 (可选, 如果提供则完全替换旧标签)"
    )
    # 管理员通常不直接修改用户密码，而是提供重置密码功能。
    # 如果需要管理员直接设置新密码，可以取消注释此字段。
    new_password: Optional[str] = Field(
        None,
        min_length=settings.user_config.password_min_len,
        max_length=settings.user_config.password_max_len,
        description=(
            f"(可选) 为用户设置新密码 ({settings.user_config.password_min_len}-"
            f"{settings.user_config.password_max_len} 位)。如果提供，将覆盖用户现有密码。"
        )
    )
# endregion

# region User Directory Entry Model
class UserDirectoryEntry(BaseModel):
    """
    Model for listing users with special roles in a public directory.
    """
    uid: str = Field(description="User ID (username)")
    nickname: Optional[str] = Field(None, description="User nickname (if available)")
    tags: List[UserTag] = Field(description="User tags indicating their roles/categories")
# endregion
