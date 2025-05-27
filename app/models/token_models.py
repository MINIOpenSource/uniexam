# -*- coding: utf-8 -*-
# region 模块导入
from typing import Optional, List, Any # 确保导入了 Any
from pydantic import BaseModel, Field

# 导入 UserTag 枚举，因为 TokenData 可能包含用户标签信息
from .user_models import UserTag
# endregion

# region Token模型 (Token)
class Token(BaseModel):
    """
    API Token模型，用于登录和刷新Token成功时的标准响应体。
    符合OAuth 2.0 Bearer Token响应的常见结构。
    """
    access_token: str = Field(description="访问令牌 (通常是一个随机生成的长字符串)")
    token_type: str = Field(default="bearer", description="令牌类型，固定为 'bearer'")
    # 可以添加 expires_in (秒) 或 user_info 等字段
    # user_info: Optional[UserPublicProfile] = None # 例如，登录成功时一并返回用户信息
# endregion

# region Token数据模型 (TokenData)
class TokenData(BaseModel):
    """
    Token内部存储或解析后承载的数据模型。
    如果使用JWT，这可以代表JWT的载荷 (payload) 部分。
    对于当前基于内存字典的简单Token方案，这是存储在 _active_tokens 中的值结构。
    """
    user_uid: str = Field(description="关联的用户唯一标识符 (uid)")
    tags: List[UserTag] = Field(default_factory=list, description="用户拥有的标签列表，用于权限控制")
    expires_at: float = Field(description="Token的过期时间戳 (time.time()的浮点数表示)")
    # 可以添加其他需要在Token中快速访问的信息，如签发时间 (iat) 等
# endregion

# region Auth Status Response Model
class AuthStatusResponse(BaseModel):
    """
    用于认证失败或特定状态响应的通用模型。
    """
    status_code: str = Field(description="表示认证结果或特定状态的字符串代码 (例如 'WRONG', 'DUPLICATE')")
    message: Optional[str] = Field(None, description="相关的消息文本 (可选)")
# endregion
