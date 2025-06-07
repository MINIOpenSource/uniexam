# -*- coding: utf-8 -*-
"""
安全相关工具模块。

此模块提供密码哈希与验证、访问Token生成与验证、
以及基于用户标签的权限检查等核心安全功能。
它使用了 passlib 进行密码处理，并实现了一个简单的内存Token存储机制。
"""
# [中文]: 此模块提供密码哈希与验证、访问Token生成与验证、以及基于用户标签的权限检查等核心安全功能。它使用了 passlib 进行密码处理，并实现了一个简单的内存Token存储机制。

# region 模块导入区域开始
import asyncio  # [中文]: 用于异步锁
import logging  # [中文]: 标准日志模块
import secrets  # [中文]: 用于生成安全的随机字符串作为Token
import time
from datetime import (
    datetime,
    timedelta,
    timezone,
)  # [中文]: 用于处理Token过期时间
from typing import Any, Dict, List, Optional, Set

from fastapi import (  # [中文]: FastAPI 相关导入
    Depends,
    HTTPException,
    Query,
    status as http_status,
)
from passlib.context import CryptContext  # [中文]: 用于密码哈希

from ..models.user_models import UserTag  # [中文]: 用户标签枚举
from .config import settings  # [中文]: 应用全局配置

# endregion 模块导入区域结束

# region 全局变量与初始化区域开始

_security_module_logger = logging.getLogger(
    __name__
)  # [中文]: 本模块专用的logger实例

# [中文]: 密码哈希上下文配置
# [中文]: 使用 bcrypt 算法，这是目前推荐的强哈希算法之一。
# [中文]: `deprecated="auto"` 会在验证旧格式哈希时自动升级到新配置（如果将来更改schemes）。
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# [中文]: 内存中的活动Token存储:
# [中文]: 结构: {"token_string": {"user_uid": "uid", "tags": ["tag_value1"], "expires_at": timestamp}}
# [中文]: 注意：此内存存储方案仅适用于单进程部署。
# [中文]: 在多进程或多实例（如使用Gunicorn多worker或Kubernetes部署）环境中，
# [中文]: 需要使用外部共享存储（如Redis, Memcached, 或数据库）来管理Token，以确保所有实例共享相同的Token状态。
_active_tokens: Dict[str, Dict[str, Any]] = {}
_token_lock = asyncio.Lock()  # [中文]: 用于对 `_active_tokens`字典进行异步操作时的并发控制
# endregion 全局变量与初始化区域结束

# region 密码工具函数区域开始


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码与哈希后的密码是否匹配。
    `passlib` 会自动从 `hashed_password` 中提取盐值和算法信息进行比较。

    参数:
        plain_password (str): 用户输入的明文密码。
        hashed_password (str): 数据库中存储的、已经`passlib`哈希过的密码字符串。

    返回:
        bool: 如果密码匹配则返回 True，否则返回 False。
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    为给定的明文密码生成哈希值。
    `passlib` 使用 `bcrypt` 算法时会自动生成并管理每个哈希的唯一盐值。

    参数:
        password (str): 需要哈希的明文密码。

    返回:
        str: 哈希后的密码字符串，包含了算法、盐值和哈希本身。
    """
    return pwd_context.hash(password)


# endregion 密码工具函数区域结束

# region Token 工具函数区域开始


async def create_access_token(user_uid: str, user_tags: List[UserTag]) -> str:
    """
    为指定用户生成一个新的访问Token，并将其存储在内存的活动Token列表中。
    Token是使用 `secrets.token_hex` 生成的伪随机十六进制字符串。

    参数:
        user_uid (str): 用户的唯一标识符。
        user_tags (List[UserTag]): 用户拥有的标签列表 (UserTag 枚举成员)。
    返回:
        str: 生成的访问Token字符串。
    """
    async with _token_lock:  # [中文]: 确保对 _active_tokens 的操作是原子性的
        token_bytes_length = (
            settings.token_length_bytes
        )  # [中文]: 从配置获取Token长度
        token = secrets.token_hex(
            token_bytes_length
        )  # [中文]: 生成安全的十六进制Token

        expires_delta = timedelta(
            hours=settings.token_expiry_hours
        )  # [中文]: Token有效期
        expires_at_timestamp = (
            time.time() + expires_delta.total_seconds()
        )  # [中文]: 计算过期时间戳

        _active_tokens[token] = {
            "user_uid": user_uid,
            "tags": [
                tag.value for tag in user_tags
            ],  # [中文]: 存储标签的字符串值
            "expires_at": expires_at_timestamp,
        }
        _security_module_logger.info(
            f"为用户 '{user_uid}' 生成新Token (部分): {token[:8]}..., "
            f"有效期至: {datetime.fromtimestamp(expires_at_timestamp, tz=timezone.utc).isoformat()}"
        )
        return token


async def validate_token_and_get_user_info(token: str) -> Optional[Dict[str, Any]]:
    """
    验证提供的Token是否有效（存在于活动列表且未过期）。

    参数:
        token (str): 客户端提供的访问Token。

    返回:
        Optional[Dict[str, Any]]: 如果Token有效，则返回包含 "user_uid" (str) 和 "tags" (List[UserTag]) 的字典。
                                   如果Token无效或过期，则返回 None，并在内部清理该过期Token。
    """
    async with _token_lock:
        token_data = _active_tokens.get(token)
        current_time = time.time()

        if token_data and token_data["expires_at"] > current_time:  # [中文]: Token有效且未过期
            try:
                # [中文]: 将存储的标签字符串值安全地转换回UserTag枚举成员
                tags_as_enum = [
                    UserTag(tag_str)
                    for tag_str in token_data.get("tags", [])
                    if tag_str
                    in UserTag._value2member_map_  # [中文]: 确保是有效的枚举值
                ]
            except ValueError as e_tag:
                _security_module_logger.error(
                    f"Token '{token[:8]}...' 中的标签列表包含无效值: "
                    f"{token_data.get('tags')}, 错误: {e_tag}. Token将被视为无效。"
                )
                _active_tokens.pop(
                    token, None
                )  # [中文]: 移除有问题的Token
                return None

            return {"user_uid": token_data["user_uid"], "tags": tags_as_enum}

        if token_data and token_data["expires_at"] <= current_time:  # [中文]: Token存在但已过期
            _security_module_logger.info(
                f"Token (部分) {token[:8]}... 已过期并被移除。"
            )
            _active_tokens.pop(token, None)  # [中文]: 从活动列表中移除
        elif not token_data:  # [中文]: Token不存在
            _security_module_logger.debug(
                f"尝试验证的Token (部分) {token[:8]}... 不存在于活动列表。"
            )
        return None


async def invalidate_token(token: str) -> None:
    """
    使指定的Token立即失效（例如，在用户登出或刷新Token时）。
    从内存中的活动Token列表中移除该Token。

    参数:
        token (str): 需要失效的Token。
    """
    async with _token_lock:
        if token in _active_tokens:
            _active_tokens.pop(token, None)
            _security_module_logger.info(
                f"Token (部分) {token[:8]}... 已被主动失效。"
            )


async def cleanup_expired_tokens_periodically():  # [中文]: 函数名已修正，原为 cleanup_expired_tokens_periodically
    """
    定期清理内存中所有已过期的Token。
    此函数应由一个后台任务周期性调用。
    """
    async with _token_lock:
        current_time = time.time()
        tokens_to_check = list(
            _active_tokens.keys()
        )  # [中文]: 创建副本进行迭代
        expired_count = 0
        for token_key in tokens_to_check:
            token_data = _active_tokens.get(token_key)
            if token_data and token_data["expires_at"] <= current_time:
                _active_tokens.pop(token_key, None)
                _security_module_logger.info(
                    f"后台任务：清理过期Token (部分): {token_key[:8]}..."
                )
                expired_count += 1
        if expired_count > 0:
            _security_module_logger.info(
                f"后台任务：共清理了 {expired_count} 个过期Token。"
            )
        # [中文]: 移除了重复的if块


async def get_all_active_token_info() -> List[Dict[str, Any]]:
    """
    获取所有当前活动Token的信息列表。

    返回:
        List[Dict[str, Any]]: 每个字典包含token_prefix, user_uid, tags, 和 expires_at (ISO格式字符串)。
    """
    active_token_details = []
    async with _token_lock:
        if not _active_tokens:
            return []

        current_time = time.time()
        # [中文]: 迭代项目副本以防修改（尽管在此处比在清理中修改的可能性小）
        for token_str, token_data in list(_active_tokens.items()):
            # [中文]: 再次检查过期时间，尽管清理任务应处理大部分，但此函数可能在清理任务之间调用
            if token_data["expires_at"] <= current_time:
                # [中文]: Token已过期，如果在此处发现，最好将其移除，尽管清理任务是主要的移除者
                # _active_tokens.pop(token_str, None) # [中文]: 如果不是 list(_active_tokens.items())，避免在未受保护的迭代中修改
                # [中文]: 为安全起见，让 cleanup_expired_tokens_periodically 处理实际移除
                continue

            active_token_details.append(
                {
                    "token_prefix": token_str[:8] + "...",
                    "user_uid": token_data["user_uid"],
                    "tags": token_data[
                        "tags"
                    ],  # [中文]: 标签已作为字符串列表存储
                    "expires_at": datetime.fromtimestamp(
                        token_data["expires_at"], tz=timezone.utc
                    ).isoformat(),
                }
            )
    return active_token_details


async def invalidate_all_tokens_for_user(user_uid: str) -> int:
    """
    使指定用户的所有活动Token立即失效。

    参数:
        user_uid (str): 需要使其Token失效的用户的UID。

    返回:
        int: 被成功失效的Token数量。
    """
    invalidated_count = 0
    tokens_to_remove = []
    async with _token_lock:
        # [中文]: 首先，识别要移除的Token，以避免在迭代时修改字典
        for token_str, token_data in _active_tokens.items():
            if token_data["user_uid"] == user_uid:
                tokens_to_remove.append(token_str)

        # [中文]: 现在，移除已识别的Token
        for token_str in tokens_to_remove:
            if (
                token_str in _active_tokens
            ):  # [中文]: 检查是否仍然存在（如果不够小心，可能已被其他进程/任务移除）
                _active_tokens.pop(token_str)
                invalidated_count += 1
                _security_module_logger.info(
                    f"已为用户 '{user_uid}' 失效Token (部分): {token_str[:8]}..."
                )

    if invalidated_count > 0:
        _security_module_logger.info(
            f"共为用户 '{user_uid}' 失效了 {invalidated_count} 个Token。"
        )
    else:
        _security_module_logger.info(
            f"未找到用户 '{user_uid}' 的活动Token进行失效操作。"
        )

    return invalidated_count


# endregion Token 工具函数区域结束

# region FastAPI 认证依赖项区域开始


async def get_current_user_info_from_token(
    token: str = Query(..., description="用户访问Token"),
) -> Dict[str, Any]:
    """
    FastAPI 依赖项：从查询参数中获取Token，验证其有效性，并返回用户信息（包括UID和标签）。
    如果Token无效、过期或用户被封禁，则会抛出相应的HTTPException。

    参数:
        token (str): 通过查询参数传递的用户访问Token。

    返回:
        Dict[str, Any]: 包含用户UID (`user_uid`) 和用户标签 (`tags`) 的字典。
    异常:
        HTTPException (401): 如果Token无效或过期。
        HTTPException (403): 如果用户账户被封禁。
    """
    user_info = await validate_token_and_get_user_info(token)
    if not user_info:
        _security_module_logger.warning(
            f"依赖项检查：无效或过期的Token尝试访问受保护资源 (部分Token: {token[:8]}...)"
        )
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的Token",
            headers={
                "WWW-Authenticate": "Bearer scheme='QueryToken'"
            },  # [中文]: 提示客户端使用QueryToken方案
        )

    if UserTag.BANNED in user_info.get("tags", []):  # [中文]: 检查用户是否被封禁
        _security_module_logger.warning(
            f"用户 '{user_info['user_uid']}' (Token: {token[:8]}...) 因被封禁而访问被拒。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="用户账户已被封禁",
        )
    return user_info


async def get_current_active_user_uid(
    user_info: Dict[str, Any] = Depends(get_current_user_info_from_token),
) -> str:
    """
    FastAPI依赖项：从 `get_current_user_info_from_token` 返回的用户信息中提取并返回当前活动用户的UID。
    此依赖项通常用于那些只需要用户UID而不需要完整用户信息的路由。

    参数:
        user_info (Dict[str, Any]): 由 `get_current_user_info_from_token` 依赖项注入的用户信息字典。
    返回:
        str: 当前活动用户的UID。
    """
    return user_info["user_uid"]


class RequireTags:
    """
    FastAPI依赖项类，用于检查当前认证用户是否拥有所有指定的必需标签。
    这个类可以被实例化并用于保护特定的API端点，确保只有具有特定权限（标签）的用户才能访问。
    """

    def __init__(self, required_tags: Set[UserTag]):
        """
        初始化权限检查器。

        参数:
            required_tags (Set[UserTag]): 一个包含必需的 `UserTag` 枚举成员的集合。
                                         用户必须拥有此集合中的所有标签才能通过检查。
        """
        self.required_tags = required_tags

    async def __call__(
        self, user_info: Dict[str, Any] = Depends(get_current_user_info_from_token)
    ) -> Dict[str, Any]:
        """
        作为FastAPI依赖项被调用时执行的权限检查逻辑。
        如果用户缺少任何必需的标签，则抛出HTTP 403 (Forbidden) 错误。

        参数:
            user_info (Dict[str, Any]): 由 `get_current_user_info_from_token` 依赖项注入的用户信息。
        返回:
            Dict[str, Any]: 如果权限检查通过，则返回原始的 `user_info` 字典。
        异常:
            HTTPException (403): 如果用户不具备所有必需的标签。
        """
        user_tags_set = set(user_info.get("tags", []))
        if not self.required_tags.issubset(
            user_tags_set
        ):  # [中文]: 检查用户是否拥有所有必需标签
            missing_tags = self.required_tags - user_tags_set
            _security_module_logger.warning(
                f"用户 '{user_info['user_uid']}' 缺少必需标签 "
                f"{[tag.value for tag in missing_tags]}，尝试访问受限资源。"
            )
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return user_info


# [中文]: 预定义的权限检查依赖项实例，方便在路由中直接使用
require_admin = RequireTags(
    {UserTag.ADMIN}
)  # [中文]: 要求用户具有ADMIN标签
require_user = RequireTags(
    {UserTag.USER}
)  # [中文]: 要求用户具有USER标签 (通常所有普通登录用户都有)
require_grader = RequireTags(
    {UserTag.GRADER}
)  # [中文]: 要求用户具有GRADER标签 (批改员)
require_examiner = RequireTags(
    {UserTag.EXAMINER}
)  # [中文]: 要求用户具有EXAMINER标签 (出题员/试卷管理员)
require_manager = RequireTags(
    {UserTag.MANAGER}
)  # [中文]: 要求用户具有MANAGER标签 (系统管理员的子集，可能有特定管理权限)
# endregion FastAPI 认证依赖项区域结束

__all__ = [
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "validate_token_and_get_user_info",
    "invalidate_token",
    "cleanup_expired_tokens_periodically",  # 函数名已修正
    "get_all_active_token_info",
    "invalidate_all_tokens_for_user",
    "get_current_user_info_from_token",
    "get_current_active_user_uid",
    "RequireTags",
    "require_admin",
    "require_user",
    "require_grader",
    "require_examiner",
    "require_manager",
    "pwd_context",  # [中文]: 公开 pwd_context 允许其他部分直接使用哈希功能
]

if __name__ == "__main__":
    # [中文]: 此模块不应作为主脚本执行。它定义了安全相关的工具，应由其他模块导入和使用。
    _security_module_logger.info(
        f"模块 {__name__} 提供了安全相关的工具函数和类，不应直接执行。"
    )
    print(
        f"模块 {__name__} 提供了安全相关的工具函数和类，不应直接执行。"
    )
