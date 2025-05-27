# region 模块导入
import time
import secrets  # 用于生成安全的随机字符串作为Token
from datetime import datetime, timedelta, timezone # 用于处理Token过期时间
from typing import Dict, Any, Optional, List, Set
import asyncio # 用于异步锁
import logging # 标准日志模块

from fastapi import Depends, HTTPException, status as http_status, Request, Query
from passlib.context import CryptContext # 用于密码哈希

# 从应用核心配置中导入设置 (使用相对导入)
from .config import settings
# 导入用户模型，用于类型提示和权限检查 (使用相对导入)
from ..models.user_models import UserTag # Corrected: models is a sibling to core

# endregion

# region 全局变量与初始化

# 获取本模块的logger实例
_security_module_logger = logging.getLogger(__name__)

# 密码哈希上下文配置，使用 bcrypt 算法
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 内存中的活动Token存储:
# 结构: {"token_string": {"user_uid": "uid", "tags": ["tag_value1", "tag_value2"], "expires_at": timestamp}}
# 注意：在多进程或多实例部署中，内存Token存储不是共享的，需要外部存储如Redis。
# 对于单进程应用，这是可行的。
_active_tokens: Dict[str, Dict[str, Any]] = {}
_token_lock = asyncio.Lock()  # 用于异步操作 _active_tokens 的锁

# endregion

# region 密码工具函数

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码与哈希后的密码是否匹配。

    参数:
        plain_password: 用户输入的明文密码。
        hashed_password: 数据库中存储的哈希密码。

    返回:
        True 如果密码匹配，否则 False。
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    生成密码的哈希值。

    参数:
        password: 用户设置的明文密码。

    返回:
        哈希后的密码字符串。
    """
    return pwd_context.hash(password)
# endregion

# region Token 工具函数

async def create_access_token(user_uid: str, user_tags: List[UserTag]) -> str:
    """
    为指定用户生成一个新的访问Token，并将其存储在内存中。

    参数:
        user_uid: 用户的唯一标识符。
        user_tags: 用户拥有的标签列表 (UserTag 枚举成员)。

    返回:
        生成的访问Token字符串。
    """
    async with _token_lock:
        # Token 长度应从 settings 中获取，假设 settings 中有 token_length_bytes 字段
        # 如果 settings 中没有定义 token_length_bytes，则需要添加或使用一个默认值
        # 例如，settings.token_config.length_bytes
        # 这里我们假设 settings 中有一个顶级的 token_length_bytes 属性
        # 如果您的 Settings 模型中没有这个，您需要先在 config.py 中添加它
        # 例如: token_length_bytes: int = 32
        token_bytes_length = getattr(settings, 'token_length_bytes', 32) # 提供一个默认值以防万一
        token = secrets.token_hex(token_bytes_length)
        
        expires_delta = timedelta(hours=settings.token_expiry_hours)
        expires_at_timestamp = time.time() + expires_delta.total_seconds()
        
        _active_tokens[token] = {
            "user_uid": user_uid,
            "tags": [tag.value for tag in user_tags], # 存储标签的字符串值
            "expires_at": expires_at_timestamp
        }
        _security_module_logger.info(
            f"为用户 '{user_uid}' 生成新Token (部分): {token[:8]}...，"
            f"有效期至: {datetime.fromtimestamp(expires_at_timestamp, tz=timezone.utc).isoformat()}"
        )
        return token

async def validate_token_and_get_user_info(token: str) -> Optional[Dict[str, Any]]:
    """
    验证提供的Token是否有效且未过期。

    参数:
        token: 客户端提供的访问Token。

    返回:
        如果Token有效，返回包含 "user_uid" (str) 和 "tags" (List[UserTag]) 的字典。
        如果Token无效或过期，返回 None，并在内部清理过期的Token。
    """
    async with _token_lock:
        token_data = _active_tokens.get(token)
        current_time = time.time()

        if token_data and token_data["expires_at"] > current_time:
            # Token有效且未过期
            try:
                # 将存储的标签字符串值转换回UserTag枚举成员
                tags_as_enum = [UserTag(tag_str) for tag_str in token_data.get("tags", [])]
            except ValueError as e_tag:
                _security_module_logger.error(
                    f"Token '{token[:8]}...' 中的标签包含无效值: "
                    f"{token_data.get('tags')}, 错误: {e_tag}"
                )
                # 如果标签无效，可以将此Token视为无效
                _active_tokens.pop(token, None) # 移除问题Token
                return None

            return {
                "user_uid": token_data["user_uid"],
                "tags": tags_as_enum
            }
        
        # 如果Token存在但已过期，或Token不存在
        if token_data and token_data["expires_at"] <= current_time:
            _security_module_logger.info(f"Token (部分) {token[:8]}... 已过期并被移除。")
            _active_tokens.pop(token, None) # 从活动Token中移除
        elif not token_data:
            _security_module_logger.debug(f"尝试验证的Token (部分) {token[:8]}... 不存在。")
            
        return None

async def invalidate_token(token: str) -> None:
    """使指定的Token失效（例如，在刷新Token或用户登出时）。"""
    async with _token_lock:
        if token in _active_tokens:
            _active_tokens.pop(token, None) # 使用 pop 的第二个参数避免 KeyError
            _security_module_logger.info(f"Token (部分) {token[:8]}... 已被主动失效。")

async def cleanup_expired_tokens_periodically():
    """
    (应由后台任务调用) 定期清理内存中所有已过期的Token。
    """
    async with _token_lock:
        current_time = time.time()
        # 创建副本进行迭代，以安全地修改原始字典
        tokens_to_check = list(_active_tokens.items())
        expired_count = 0
        for t_key, data in tokens_to_check:
            if data["expires_at"] <= current_time:
                if _active_tokens.pop(t_key, None): # 确保只在实际移除时计数和记录日志
                    _security_module_logger.info(f"后台任务：清理过期Token (部分): {t_key[:8]}...")
                    expired_count += 1
        if expired_count > 0:
            _security_module_logger.info(f"后台任务：共清理了 {expired_count} 个过期Token。")

# endregion

# region FastAPI 认证依赖项

async def get_current_user_info_from_token(
    token: str = Query(..., description="用户访问Token")
) -> Dict[str, Any]:
    """
    FastAPI依赖项：从查询参数获取Token，验证它，并返回用户信息（uid, tags）。
    如果Token无效或用户被封禁，则抛出相应的HTTP错误。
    """
    user_info = await validate_token_and_get_user_info(token)
    if not user_info:
        _security_module_logger.warning(
            f"依赖项检查：无效或过期的Token尝试访问受保护资源 (部分Token: {token[:8]}...)"
        )
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token", # 响应描述使用英文
            headers={"WWW-Authenticate": "Bearer scheme='QueryToken'"}, # 更明确的提示
        )
    
    # 检查用户是否被封禁
    # user_info['tags'] 现在应该是 List[UserTag]
    if UserTag.BANNED in user_info.get("tags", []):
        _security_module_logger.warning(
            f"用户 '{user_info['user_uid']}' (Token: {token[:8]}...) 因被封禁而访问被拒。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="User account is banned",
        )
    return user_info

async def get_current_active_user_uid(
    user_info: Dict[str, Any] = Depends(get_current_user_info_from_token)
) -> str:
    """FastAPI依赖项：从已验证的用户信息中获取当前活动用户的UID。"""
    return user_info["user_uid"]

class RequireTags:
    """
    FastAPI依赖项类，用于检查当前用户是否拥有所有必需的标签。
    可以用于接口的权限控制。
    """
    def __init__(self, required_tags: Set[UserTag]):
        """
        初始化权限检查器。

        参数:
            required_tags: 一个包含必需 UserTag 枚举成员的集合。
        """
        self.required_tags = required_tags

    async def __call__(self, user_info: Dict[str, Any] = Depends(get_current_user_info_from_token)) -> Dict[str, Any]:
        """
        执行权限检查。如果用户缺少任何必需标签，则抛出HTTP 403错误。

        参数:
            user_info: 从 `get_current_user_info_from_token` 获取的用户信息。

        返回:
            如果检查通过，返回原始的 `user_info`，以便后续路由函数可能需要用到。
        """
        # user_info['tags'] 已经是 List[UserTag]
        user_tags_set = set(user_info.get("tags", []))
        if not self.required_tags.issubset(user_tags_set):
            missing_tags = self.required_tags - user_tags_set
            _security_module_logger.warning(
                f"用户 '{user_info['user_uid']}' 缺少必需标签 "
                f"{[tag.value for tag in missing_tags]}，"
                f"尝试访问受限资源。"
            )
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions", # 响应描述使用英文
            )
        return user_info

# 预定义的权限检查依赖项实例，供路由使用
require_admin = RequireTags({UserTag.ADMIN})
require_user = RequireTags({UserTag.USER}) # 确保是普通用户（至少有USER标签）
require_grader = RequireTags({UserTag.GRADER})
require_examiner = RequireTags({UserTag.EXAMINER})
require_manager = RequireTags({UserTag.MANAGER})

# endregion
