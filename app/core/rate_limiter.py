# -*- coding: utf-8 -*-
"""
速率限制模块 (Rate Limiting Module)。

此模块提供了基于IP地址和操作类型的速率限制功能。
它使用内存中的时间戳列表来跟踪请求频率，并根据配置文件中定义的规则进行限制。
主要功能是 `is_rate_limited` 函数，用于检查特定请求是否应被阻止。

(This module provides rate limiting functionality based on IP address and operation type.
It uses in-memory lists of timestamps to track request frequency and applies limits
based on rules defined in the configuration file. The main function is `is_rate_limited`,
used to check if a specific request should be blocked.)
"""

# region 模块导入 (Module Imports)
import logging
import time
from typing import Dict, List, Optional

from fastapi import (
    Request,
)  # 导入FastAPI的Request对象 (Import FastAPI's Request object)

# from .security import get_current_user_info_from_token # (可选) 如需基于用户标签的速率限制
from ..models.user_models import UserTag  # 用户标签枚举
from .config import settings  # 应用全局配置

# endregion

# region 全局变量与初始化 (Global Variables & Initialization)

_rate_limiter_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例

# 用于速率限制的数据结构: (Data structures for rate limiting)
# 键为IP地址 (str)，值为对应操作的请求时间戳列表 (List[float])
# (Key is IP address (str), value is a list of request timestamps (List[float]) for the corresponding action)
# 分开存储不同操作的速率限制数据 (Store rate limit data for different actions separately)
ip_exam_request_timestamps: Dict[
    str, List[float]
] = {}  # 获取新试卷 ("get_exam" action)
ip_auth_attempt_timestamps: Dict[
    str, List[float]
] = {}  # 登录/注册等认证尝试 ("auth_attempts" action)

# endregion

# region 速率限制核心逻辑 (Rate Limiting Core Logic)


def is_rate_limited(
    client_ip: str,
    action_type: str,  # 例如 "get_exam", "auth_attempts" (e.g., "get_exam", "auth_attempts")
    user_tags: Optional[List[UserTag]] = None,
) -> bool:
    """
    检查指定IP和操作类型是否超出速率限制。
    (Checks if the specified IP and action type have exceeded the rate limit.)

    参数 (Args):
        client_ip (str): 客户端的IP地址。(Client's IP address.)
        action_type (str): 操作类型，用于从配置中查找对应的限制规则。
                           (Action type, used to find corresponding limit rules in config.)
        user_tags (Optional[List[UserTag]]): (可选) 当前用户的标签列表，用于应用特定用户类型的限制。
                                              ((Optional) List of current user's tags, for applying
                                               user-type-specific limits.)

    返回 (Returns):
        bool: True 如果请求应被限制，否则 False。(True if the request should be limited, False otherwise.)
    """
    current_time = time.time()  # 获取当前时间戳

    # 根据用户标签确定使用哪套速率限制规则
    # (Determine which set of rate limit rules to use based on user tags)
    # 默认为 "default_user"，如果用户有 "limited" 标签，则使用 "limited_user"
    # (Defaults to "default_user"; if user has "limited" tag, use "limited_user")
    # 管理员 (admin) 通常不受此速率限制 (此判断应在调用此函数前完成)
    # (Admins are typically not rate-limited (this check should be done before calling this function))
    limit_config_key = "default_user"
    if user_tags and UserTag.LIMITED in user_tags:
        limit_config_key = "limited_user"

    # 从 settings 中获取对应操作类型的速率限制配置
    # (Get rate limit config for the action type from settings)
    user_type_limits = settings.rate_limits.get(limit_config_key)
    if not user_type_limits:
        _rate_limiter_logger.error(
            f"未找到用户类型 '{limit_config_key}' 的速率限制配置。默认不限制。"
            f"(Rate limit config not found for user type '{limit_config_key}'. Defaulting to no limit.)"
        )
        return False  # 配置错误，默认不限制 (Configuration error, default to no limit)

    action_limit_config = getattr(user_type_limits, action_type, None)
    if not action_limit_config:
        _rate_limiter_logger.error(
            f"未在用户类型 '{limit_config_key}' 中找到操作 '{action_type}' 的速率限制配置。默认不限制。"
            f"(Rate limit config not found for action '{action_type}' in user type '{limit_config_key}'. Defaulting to no limit.)"
        )
        return False  # 配置错误，默认不限制

    # 选择对应操作的时间戳字典
    # (Select the timestamp dictionary for the corresponding action)
    if action_type == "get_exam":
        timestamps_dict_ref = ip_exam_request_timestamps
    elif action_type == "auth_attempts":
        timestamps_dict_ref = ip_auth_attempt_timestamps
    else:
        _rate_limiter_logger.warning(
            f"未知的速率限制操作类型 (Unknown rate limit action type): {action_type}。默认不限制。"
        )
        return False  # 未知类型，默认不限制

    ip_timestamps = timestamps_dict_ref.get(client_ip, [])

    # 清理所有早于 (当前时间 - 窗口期) 的旧时间戳
    # (Remove all old timestamps earlier than (current_time - window_period))
    # action_limit_config.window 是秒数 (action_limit_config.window is in seconds)
    valid_timestamps = [
        ts for ts in ip_timestamps if current_time - ts < action_limit_config.window
    ]

    if len(valid_timestamps) >= action_limit_config.limit:
        # 已达到或超过限制 (Limit reached or exceeded)
        _rate_limiter_logger.info(
            f"IP {client_ip} 的操作 '{action_type}' (用户类型 (User Type): {limit_config_key}) 超出速率限制 (Rate limit exceeded): "
            f"{len(valid_timestamps)} 次 (requests) >= {action_limit_config.limit} 次 / {action_limit_config.window} 秒 (s)。"
        )
        timestamps_dict_ref[client_ip] = (
            valid_timestamps  # 更新为清理后的列表（可选）(Update with cleaned list (optional))
        )
        return True  # 应被限制 (Should be limited)

    # 未超限，记录当前时间戳 (Not exceeded, record current timestamp)
    valid_timestamps.append(current_time)
    timestamps_dict_ref[client_ip] = valid_timestamps
    _rate_limiter_logger.debug(
        f"IP {client_ip} 的操作 '{action_type}' (用户类型 (User Type): {limit_config_key}) 未超限 (Not rate limited)。 "
        f"当前计数 (Current count): {len(valid_timestamps)} / {action_limit_config.limit}。"
    )
    return False  # 不限制 (Not limited)


# endregion

__all__ = [
    "is_rate_limited",
    # "rate_limit_dependency", # 这是一个概念性的、未实际使用的依赖项 (Conceptual, unused dependency)
    # 导出这些全局变量是为了可能的外部监控或管理，但通常不建议直接从其他模块修改它们
    # (Exporting these globals for potential external monitoring/management, but direct modification
    #  from other modules is generally not recommended)
    "ip_exam_request_timestamps",
    "ip_auth_attempt_timestamps",
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了速率限制相关的函数和数据结构，应由其他模块导入和使用。
    # (This module should not be executed as the main script. It defines rate limiting functions
    #  and data structures, and should be imported and used by other modules.)
    _rate_limiter_logger.info(f"模块 {__name__} 提供了速率限制功能，不应直接执行。")
    print(
        f"模块 {__name__} 提供了速率限制功能，不应直接执行。 (This module provides rate limiting functionality and should not be executed directly.)"
    )

# region FastAPI 依赖项 (用于路由中直接应用速率限制) - 概念性 (FastAPI Dependency - Conceptual)

# 注意：以下依赖项 `rate_limit_dependency` 是一个设计概念，
# 在当前版本的应用中并未直接在路由上使用。
# 实际的速率限制检查是通过在路由处理函数内部调用 `is_rate_limited` 来完成的。
# 这是因为依赖项需要预先知道 `action_type` 和 `user_tags`，这使得通用依赖项难以实现，
# 或者需要更复杂的依赖项链。

# (Note: The following dependency `rate_limit_dependency` is a design concept and
# is not directly used in routes in the current version of the application.
# Actual rate limit checks are performed by calling `is_rate_limited` within
# route handler functions. This is because the dependency would need to know
# `action_type` and `user_tags` beforehand, making a generic dependency
# complex to implement, or requiring more intricate dependency chains.)


async def rate_limit_dependency(
    request: Request,
    action_type: str,  # 需要在路由定义中通过某种方式传递此操作类型
    # (This action type would need to be passed somehow in the route definition)
    # user_tags: Optional[List[UserTag]] = Depends(get_current_user_tags_optional) # 示例：获取用户标签的依赖
    # (Example: dependency to get user tags)
):
    """
    一个通用的速率限制FastAPI依赖项（概念性演示）。
    (A generic rate-limiting FastAPI dependency (conceptual demonstration).)

    实际使用时，可能需要为每个受限操作创建特定的依赖项，
    或者在路由函数内部调用 `is_rate_limited`（当前采用此方式）。
    (In practice, specific dependencies might be needed for each limited action,
    or `is_rate_limited` is called within route functions (current approach).)
    """
    # # 示例实现逻辑 (Example implementation logic):
    # client_ip = get_client_ip_from_request(request) # 使用项目中的工具函数获取IP (Use helper to get IP)
    # # 假设 user_tags 已通过另一个依赖项获取 (Assume user_tags obtained via another dependency)
    # current_user_tags: Optional[List[UserTag]] = getattr(request.state, "user_tags", None)

    # # 管理员通常不受速率限制 (Admins usually bypass rate limits)
    # if current_user_tags and UserTag.ADMIN in current_user_tags:
    #     return

    # if is_rate_limited(client_ip, action_type, current_user_tags):
    #     _rate_limiter_logger.warning(f"请求被速率限制。IP: {client_ip}, 操作: {action_type}")
    #     raise HTTPException(
    #         status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
    #         detail=f"操作 '{action_type}' 请求过于频繁，请稍后再试。 (Rate limit exceeded for action: {action_type}. Please try again later.)",
    #     )
    pass  # 当前为空操作，实际限制在路由处理函数中完成 (Currently a no-op; actual limiting in route handlers)


# endregion
