# -*- coding: utf-8 -*-
"""
安全相关工具模块 (Security-related Utility Module)。

此模块提供密码哈希与验证、访问Token生成与验证、
以及基于用户标签的权限检查等核心安全功能。
它使用了 passlib 进行密码处理，并实现了一个简单的内存Token存储机制。

(This module provides core security functionalities such as password hashing and verification,
access token generation and validation, and permission checks based on user tags.
It uses passlib for password handling and implements a simple in-memory token storage mechanism.)
"""

# region 模块导入 (Module Imports)
import asyncio  # 用于异步锁 (For asynchronous locks)
import logging  # 标准日志模块 (Standard logging module)
import secrets  # 用于生成安全的随机字符串作为Token (For generating secure random strings as tokens)
import time
from datetime import (
    datetime,
    timedelta,
    timezone,
)  # 用于处理Token过期时间 (For handling token expiration times)
from typing import Any, Dict, List, Optional, Set

from fastapi import (  # FastAPI 相关导入
    Depends,
    HTTPException,
    Query,
    status as http_status,
)
from passlib.context import CryptContext  # 用于密码哈希 (For password hashing)

from ..models.user_models import UserTag  # 用户标签枚举 (UserTag enum from models)
from .config import settings  # 应用全局配置 (Application global settings)

# endregion

# region 全局变量与初始化 (Global Variables & Initialization)

_security_module_logger = logging.getLogger(
    __name__
)  # 本模块专用的logger实例 (Logger instance for this module)

# 密码哈希上下文配置 (Password hashing context configuration)
# 使用 bcrypt 算法，这是目前推荐的强哈希算法之一。
# (Using bcrypt algorithm, one of the currently recommended strong hashing algorithms.)
# `deprecated="auto"` 会在验证旧格式哈希时自动升级到新配置（如果将来更改schemes）。
# (`deprecated="auto"` will automatically upgrade to the new configuration when validating old format hashes
#  (if schemes are changed in the future).)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 内存中的活动Token存储: (In-memory active token storage)
# 结构 (Structure): {"token_string": {"user_uid": "uid", "tags": ["tag_value1"], "expires_at": timestamp}}
# 注意：此内存存储方案仅适用于单进程部署。
# (Note: This in-memory storage scheme is only suitable for single-process deployments.)
# 在多进程或多实例（如使用Gunicorn多worker或Kubernetes部署）环境中，
# 需要使用外部共享存储（如Redis, Memcached, 或数据库）来管理Token，以确保所有实例共享相同的Token状态。
# (In multi-process or multi-instance environments (e.g., using Gunicorn multi-workers or Kubernetes),
#  external shared storage (like Redis, Memcached, or a database) is needed to manage tokens
#  to ensure all instances share the same token state.)
_active_tokens: Dict[str, Dict[str, Any]] = {}
_token_lock = asyncio.Lock()  # 用于对 `_active_tokens`字典进行异步操作时的并发控制
# (Async lock for concurrent control of operations on `_active_tokens` dictionary)
# endregion

# region 密码工具函数 (Password Utility Functions)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码与哈希后的密码是否匹配。
    `passlib` 会自动从 `hashed_password` 中提取盐值和算法信息进行比较。

    (Verifies if the plaintext password matches the hashed password.
    `passlib` automatically extracts salt and algorithm information from `hashed_password` for comparison.)

    参数 (Args):
        plain_password (str): 用户输入的明文密码。(User-input plaintext password.)
        hashed_password (str): 数据库中存储的、已经`passlib`哈希过的密码字符串。
                               (The `passlib`-hashed password string stored in the database.)

    返回 (Returns):
        bool: 如果密码匹配则返回 True，否则返回 False。(True if passwords match, False otherwise.)
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    为给定的明文密码生成哈希值。
    `passlib` 使用 `bcrypt` 算法时会自动生成并管理每个哈希的唯一盐值。

    (Generates a hash for the given plaintext password.
    When using the `bcrypt` algorithm, `passlib` automatically generates and manages
    a unique salt for each hash.)

    参数 (Args):
        password (str): 需要哈希的明文密码。(Plaintext password to be hashed.)

    返回 (Returns):
        str: 哈希后的密码字符串，包含了算法、盐值和哈希本身。
             (The hashed password string, which includes the algorithm, salt, and the hash itself.)
    """
    return pwd_context.hash(password)


# endregion

# region Token 工具函数 (Token Utility Functions)


async def create_access_token(user_uid: str, user_tags: List[UserTag]) -> str:
    """
    为指定用户生成一个新的访问Token，并将其存储在内存的活动Token列表中。
    Token是使用 `secrets.token_hex` 生成的伪随机十六进制字符串。

    (Generates a new access token for the specified user and stores it in the in-memory
    active token list. The token is a pseudo-random hexadecimal string generated using `secrets.token_hex`.)

    参数 (Args):
        user_uid (str): 用户的唯一标识符。(User's unique identifier.)
        user_tags (List[UserTag]): 用户拥有的标签列表 (UserTag 枚举成员)。
                                     (List of tags the user possesses (UserTag enum members).)
    返回 (Returns):
        str: 生成的访问Token字符串。(The generated access token string.)
    """
    async with (
        _token_lock
    ):  # 确保对 _active_tokens 的操作是原子性的 (Ensure atomic operation on _active_tokens)
        token_bytes_length = (
            settings.token_length_bytes
        )  # 从配置获取Token长度 (Get token length from config)
        token = secrets.token_hex(
            token_bytes_length
        )  # 生成安全的十六进制Token (Generate secure hex token)

        expires_delta = timedelta(
            hours=settings.token_expiry_hours
        )  # Token有效期 (Token validity period)
        expires_at_timestamp = (
            time.time() + expires_delta.total_seconds()
        )  # 计算过期时间戳 (Calculate expiration timestamp)

        _active_tokens[token] = {
            "user_uid": user_uid,
            "tags": [
                tag.value for tag in user_tags
            ],  # 存储标签的字符串值 (Store string values of tags)
            "expires_at": expires_at_timestamp,
        }
        _security_module_logger.info(
            f"为用户 '{user_uid}' 生成新Token (部分) (Generated new token (partial) for user '{user_uid}'): {token[:8]}..., "
            f"有效期至 (Expires at): {datetime.fromtimestamp(expires_at_timestamp, tz=timezone.utc).isoformat()}"
        )
        return token


async def validate_token_and_get_user_info(token: str) -> Optional[Dict[str, Any]]:
    """
    验证提供的Token是否有效（存在于活动列表且未过期）。
    (Validates if the provided token is valid (exists in the active list and has not expired).)

    参数 (Args):
        token (str): 客户端提供的访问Token。(Access token provided by the client.)

    返回 (Returns):
        Optional[Dict[str, Any]]: 如果Token有效，则返回包含 "user_uid" (str) 和 "tags" (List[UserTag]) 的字典。
                                   如果Token无效或过期，则返回 None，并在内部清理该过期Token。
                                   (If the token is valid, returns a dictionary containing "user_uid" (str)
                                    and "tags" (List[UserTag]). If the token is invalid or expired,
                                    returns None and internally cleans up the expired token.)
    """
    async with _token_lock:
        token_data = _active_tokens.get(token)
        current_time = time.time()

        if token_data and token_data["expires_at"] > current_time:  # Token有效且未过期
            try:
                # 将存储的标签字符串值安全地转换回UserTag枚举成员
                # (Safely convert stored tag string values back to UserTag enum members)
                tags_as_enum = [
                    UserTag(tag_str)
                    for tag_str in token_data.get("tags", [])
                    if tag_str
                    in UserTag._value2member_map_  # 确保是有效的枚举值 (Ensure it's a valid enum value)
                ]
            except ValueError as e_tag:
                _security_module_logger.error(
                    f"Token '{token[:8]}...' 中的标签列表包含无效值 (Token '{token[:8]}...' tag list contains invalid value): "
                    f"{token_data.get('tags')}, 错误 (Error): {e_tag}. Token将被视为无效 (Token will be treated as invalid)."
                )
                _active_tokens.pop(
                    token, None
                )  # 移除有问题的Token (Remove problematic token)
                return None

            return {"user_uid": token_data["user_uid"], "tags": tags_as_enum}

        if token_data and token_data["expires_at"] <= current_time:  # Token存在但已过期
            _security_module_logger.info(
                f"Token (部分) (Token (partial)) {token[:8]}... 已过期并被移除 (expired and removed)."
            )
            _active_tokens.pop(token, None)  # 从活动列表中移除
        elif not token_data:  # Token不存在
            _security_module_logger.debug(
                f"尝试验证的Token (部分) (Attempted to validate token (partial)) {token[:8]}... 不存在于活动列表 (not found in active list)."
            )
        return None


async def invalidate_token(token: str) -> None:
    """
    使指定的Token立即失效（例如，在用户登出或刷新Token时）。
    从内存中的活动Token列表中移除该Token。
    (Invalidates the specified token immediately (e.g., on user logout or token refresh).
    Removes the token from the in-memory active token list.)

    参数 (Args):
        token (str): 需要失效的Token。(Token to be invalidated.)
    """
    async with _token_lock:
        if token in _active_tokens:
            _active_tokens.pop(token, None)
            _security_module_logger.info(
                f"Token (部分) (Token (partial)) {token[:8]}... 已被主动失效 (actively invalidated)."
            )


async def cleanup_expired_tokens_periodically():  # 函数名已修正，原为 cleanup_expired_tokens_periodically
    """
    定期清理内存中所有已过期的Token。
    此函数应由一个后台任务周期性调用。
    (Periodically cleans up all expired tokens from memory.
    This function should be called periodically by a background task.)
    """
    async with _token_lock:
        current_time = time.time()
        tokens_to_check = list(
            _active_tokens.keys()
        )  # 创建副本进行迭代 (Create a copy for iteration)
        expired_count = 0
        for token_key in tokens_to_check:
            token_data = _active_tokens.get(token_key)
            if token_data and token_data["expires_at"] <= current_time:
                _active_tokens.pop(token_key, None)
                _security_module_logger.info(
                    f"后台任务：清理过期Token (部分) (Background task: Cleaned expired token (partial)): {token_key[:8]}..."
                )
                expired_count += 1
        if expired_count > 0:
            _security_module_logger.info(
                f"后台任务：共清理了 {expired_count} 个过期Token。(Background task: Cleaned a total of {expired_count} expired tokens.)"
            )


# endregion

# region FastAPI 认证依赖项 (FastAPI Authentication Dependencies)


async def get_current_user_info_from_token(
    token: str = Query(..., description="用户访问Token (User access token)"),
) -> Dict[str, Any]:
    """
    FastAPI 依赖项：从查询参数中获取Token，验证其有效性，并返回用户信息（包括UID和标签）。
    如果Token无效、过期或用户被封禁，则会抛出相应的HTTPException。

    (FastAPI Dependency: Gets the token from query parameters, validates its effectiveness,
    and returns user information (including UID and tags).
    Throws corresponding HTTPException if the token is invalid, expired, or the user is banned.)

    参数 (Args):
        token (str): 通过查询参数传递的用户访问Token。(User access token passed via query parameter.)

    返回 (Returns):
        Dict[str, Any]: 包含用户UID (`user_uid`) 和用户标签 (`tags`) 的字典。
                        (Dictionary containing user UID (`user_uid`) and user tags (`tags`).)
    异常 (Raises):
        HTTPException (401): 如果Token无效或过期。(If token is invalid or expired.)
        HTTPException (403): 如果用户账户被封禁。(If user account is banned.)
    """
    user_info = await validate_token_and_get_user_info(token)
    if not user_info:
        _security_module_logger.warning(
            f"依赖项检查：无效或过期的Token尝试访问受保护资源 (部分Token: {token[:8]}...)"
            f"(Dependency check: Invalid or expired token tried to access protected resource (Partial Token: {token[:8]}...))"
        )
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的Token", # 完全中文 (Fully Chinese)
            headers={
                "WWW-Authenticate": "Bearer scheme='QueryToken'"
            },  # 提示客户端使用QueryToken方案
        )

    if UserTag.BANNED in user_info.get("tags", []):  # 检查用户是否被封禁
        _security_module_logger.warning(
            f"用户 '{user_info['user_uid']}' (Token: {token[:8]}...) 因被封禁而访问被拒。"
            f"(User '{user_info['user_uid']}' (Token: {token[:8]}...) access denied due to being banned.)"
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="用户账户已被封禁", # 完全中文 (Fully Chinese)
        )
    return user_info


async def get_current_active_user_uid(
    user_info: Dict[str, Any] = Depends(get_current_user_info_from_token),
) -> str:
    """
    FastAPI依赖项：从 `get_current_user_info_from_token` 返回的用户信息中提取并返回当前活动用户的UID。
    此依赖项通常用于那些只需要用户UID而不需要完整用户信息的路由。

    (FastAPI Dependency: Extracts and returns the UID of the current active user from the user
    information returned by `get_current_user_info_from_token`. This dependency is typically
    used for routes that only require the user UID and not the full user information.)

    参数 (Args):
        user_info (Dict[str, Any]): 由 `get_current_user_info_from_token` 依赖项注入的用户信息字典。
                                     (User information dictionary injected by the
                                      `get_current_user_info_from_token` dependency.)
    返回 (Returns):
        str: 当前活动用户的UID。(UID of the current active user.)
    """
    return user_info["user_uid"]


# 旧的HTTP Basic认证逻辑 (Old HTTP Basic auth logic - to be removed if not used)
# async def _authenticate_admin_user_http_basic(credentials: HTTPBasicCredentials = Depends(HTTPBasic())):
#     """
#     内部辅助函数：验证HTTP Basic认证凭据是否为预设的管理员用户名和密码。
#     (Internal helper function: Validates if HTTP Basic auth credentials match preset admin username/password.)
#     """
#     correct_username = secrets.compare_digest(credentials.username, settings.admin_username)
#     correct_password = secrets.compare_digest(credentials.password, settings.admin_password)
#     if not (correct_username and correct_password):
#         _security_module_logger.warning(
#             f"管理员HTTP Basic认证失败，用户名: '{credentials.username}'"
#             f"(Admin HTTP Basic auth failed for username: '{credentials.username}')"
#         )
#         raise HTTPException(
#             status_code=http_status.HTTP_401_UNAUTHORIZED,
#             detail="管理员凭据错误 (Incorrect admin credentials)",
#             headers={"WWW-Authenticate": "Basic"},
#         )
#     # 注意：此基础认证不直接返回用户模型或标签，仅用于访问控制。
#     # (Note: This basic auth doesn't directly return a user model or tags, only for access control.)
#     _security_module_logger.info(f"管理员 '{credentials.username}' 通过HTTP Basic认证成功。")
#     return credentials.username

# async def get_current_admin_user(admin_username: str = Depends(_authenticate_admin_user_http_basic)):
#     """
#     FastAPI依赖项：确保当前用户通过HTTP Basic认证为管理员。
#     (FastAPI Dependency: Ensures the current user is authenticated as admin via HTTP Basic.)
#     """
#     # 此函数主要用于依赖注入，实际的用户名已在 _authenticate_admin_user_http_basic 中验证。
#     # (This function is mainly for dependency injection; actual username is validated in _authenticate_admin_user_http_basic.)
#     return admin_username


class RequireTags:
    """
    FastAPI依赖项类，用于检查当前认证用户是否拥有所有指定的必需标签。
    这个类可以被实例化并用于保护特定的API端点，确保只有具有特定权限（标签）的用户才能访问。

    (FastAPI dependency class used to check if the currently authenticated user possesses
    all specified required tags. This class can be instantiated and used to protect specific
    API endpoints, ensuring that only users with particular permissions (tags) can access them.)
    """

    def __init__(self, required_tags: Set[UserTag]):
        """
        初始化权限检查器。(Initializes the permission checker.)

        参数 (Args):
            required_tags (Set[UserTag]): 一个包含必需的 `UserTag` 枚举成员的集合。
                                         用户必须拥有此集合中的所有标签才能通过检查。
                                         (A set containing required `UserTag` enum members.
                                          The user must possess all tags in this set to pass the check.)
        """
        self.required_tags = required_tags

    async def __call__(
        self, user_info: Dict[str, Any] = Depends(get_current_user_info_from_token)
    ) -> Dict[str, Any]:
        """
        作为FastAPI依赖项被调用时执行的权限检查逻辑。
        如果用户缺少任何必需的标签，则抛出HTTP 403 (Forbidden) 错误。

        (Permission checking logic executed when called as a FastAPI dependency.
        Throws an HTTP 403 (Forbidden) error if the user lacks any required tags.)

        参数 (Args):
            user_info (Dict[str, Any]): 由 `get_current_user_info_from_token` 依赖项注入的用户信息。
                                         (User information injected by `get_current_user_info_from_token`.)
        返回 (Returns):
            Dict[str, Any]: 如果权限检查通过，则返回原始的 `user_info` 字典。
                            (If permission check passes, returns the original `user_info` dictionary.)
        异常 (Raises):
            HTTPException (403): 如果用户不具备所有必需的标签。(If the user does not possess all required tags.)
        """
        user_tags_set = set(user_info.get("tags", []))
        if not self.required_tags.issubset(
            user_tags_set
        ):  # 检查用户是否拥有所有必需标签
            missing_tags = self.required_tags - user_tags_set
            _security_module_logger.warning(
                f"用户 '{user_info['user_uid']}' 缺少必需标签 (User '{user_info['user_uid']}' missing required tags) "
                f"{[tag.value for tag in missing_tags]}，尝试访问受限资源 (attempting to access restricted resource)."
            )
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="权限不足 (Insufficient permissions)",
            )
        return user_info


# 预定义的权限检查依赖项实例，方便在路由中直接使用
# (Predefined permission check dependency instances for direct use in routes)
require_admin = RequireTags(
    {UserTag.ADMIN}
)  # 要求用户具有ADMIN标签 (Requires ADMIN tag)
require_user = RequireTags(
    {UserTag.USER}
)  # 要求用户具有USER标签 (通常所有普通登录用户都有)
# (Requires USER tag (typically all normal logged-in users have this))
require_grader = RequireTags(
    {UserTag.GRADER}
)  # 要求用户具有GRADER标签 (批改员) (Requires GRADER tag (grader))
require_examiner = RequireTags(
    {UserTag.EXAMINER}
)  # 要求用户具有EXAMINER标签 (出题员/试卷管理员)
# (Requires EXAMINER tag (question/paper admin))
require_manager = RequireTags(
    {UserTag.MANAGER}
)  # 要求用户具有MANAGER标签 (系统管理员的子集，可能有特定管理权限)
# (Requires MANAGER tag (subset of admin, may have specific management perms))
# endregion

__all__ = [
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "validate_token_and_get_user_info",
    "invalidate_token",
    "cleanup_expired_tokens_periodically",  # 函数名已修正
    "get_current_user_info_from_token",
    "get_current_active_user_uid",
    # "get_current_admin_user", # 已移除 (Removed)
    "RequireTags",
    "require_admin",
    "require_user",
    "require_grader",
    "require_examiner",
    "require_manager",
    "pwd_context",  # 公开 pwd_context 允许其他部分直接使用哈希功能
    # (Exposing pwd_context allows other parts to use hashing functions directly)
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了安全相关的工具，应由其他模块导入和使用。
    # (This module should not be executed as the main script. It defines security-related tools
    #  and should be imported and used by other modules.)
    _security_module_logger.info(
        f"模块 {__name__} 提供了安全相关的工具函数和类，不应直接执行。"
    )
    print(
        f"模块 {__name__} 提供了安全相关的工具函数和类，不应直接执行。 (This module provides security-related utility functions and classes and should not be executed directly.)"
    )
