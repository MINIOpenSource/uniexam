# -*- coding: utf-8 -*-
"""
速率限制模块 (Rate Limiting Module)。

此模块提供了基于IP地址和操作类型的速率限制功能。
它使用内存中的时间戳列表来跟踪请求频率，并根据配置文件中定义的规则进行限制。
主要功能是 `is_rate_limited` 函数，用于检查特定请求是否应被阻止。
"""
# [中文]: 此模块提供了基于IP地址和操作类型的速率限制功能。它使用内存中的时间戳列表来跟踪请求频率，并根据配置文件中定义的规则进行限制。主要功能是 `is_rate_limited` 函数，用于检查特定请求是否应被阻止。

# region 模块导入区域开始
import logging
import time
from typing import Dict, List, Optional

from fastapi import (
    Request,
)  # [中文]: 导入FastAPI的Request对象
# [中文]: # from .security import get_current_user_info_from_token # (可选) 如需基于用户标签的速率限制
from ..models.user_models import UserTag  # 用户标签枚举
from .config import settings  # 应用全局配置

# endregion 模块导入区域结束

# region 全局变量与初始化区域开始

_rate_limiter_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例

# [中文]: 用于速率限制的数据结构
# [中文]: 键为IP地址 (str)，值为对应操作的请求时间戳列表 (List[float])
# [中文]: (Key is IP address (str), value is a list of request timestamps (List[float]) for the corresponding action)
# [中文]: 分开存储不同操作的速率限制数据
ip_exam_request_timestamps: Dict[
    str, List[float]
] = {}  # [中文]: 获取新试卷 (操作类型 "get_exam")
ip_auth_attempt_timestamps: Dict[
    str, List[float]
] = {}  # [中文]: 登录/注册等认证尝试 (操作类型 "auth_attempts")

# endregion 全局变量与初始化区域结束

# region 速率限制核心逻辑区域开始


def is_rate_limited(
    client_ip: str,
    action_type: str,  # [中文]: 例如 "get_exam", "auth_attempts"
    user_tags: Optional[List[UserTag]] = None,
) -> bool:
    """
    检查指定IP和操作类型是否超出速率限制。

    参数:
        client_ip (str): 客户端的IP地址。
        action_type (str): 操作类型，用于从配置中查找对应的限制规则。
        user_tags (Optional[List[UserTag]]): (可选) 当前用户的标签列表，用于应用特定用户类型的限制。

    返回:
        bool: 如果请求应被限制则返回 True，否则返回 False。
    """
    current_time = time.time()  # 获取当前时间戳

    # [中文]: 根据用户标签确定使用哪套速率限制规则
    # [中文]: 默认为 "default_user"，如果用户有 "limited" 标签，则使用 "limited_user"
    # [中文]: 管理员 (admin) 通常不受此速率限制 (此判断应在调用此函数前完成)
    limit_config_key = "default_user"
    if user_tags and UserTag.LIMITED in user_tags:
        limit_config_key = "limited_user"

    # [中文]: 从 settings 中获取对应操作类型的速率限制配置
    user_type_limits = settings.rate_limits.get(limit_config_key)
    if not user_type_limits:
        _rate_limiter_logger.error(
            f"未找到用户类型 '{limit_config_key}' 的速率限制配置。默认不限制。"
        )
        return False  # [中文]: 配置错误，默认不限制

    action_limit_config = getattr(user_type_limits, action_type, None)
    if not action_limit_config:
        _rate_limiter_logger.error(
            f"未在用户类型 '{limit_config_key}' 中找到操作 '{action_type}' 的速率限制配置。默认不限制。"
        )
        return False  # [中文]: 配置错误，默认不限制

    # [中文]: 选择对应操作的时间戳字典
    if action_type == "get_exam":
        timestamps_dict_ref = ip_exam_request_timestamps
    elif action_type == "auth_attempts":
        timestamps_dict_ref = ip_auth_attempt_timestamps
    else:
        _rate_limiter_logger.warning(
            f"未知的速率限制操作类型: {action_type}。默认不限制。"
        )
        return False  # [中文]: 未知类型，默认不限制

    ip_timestamps = timestamps_dict_ref.get(client_ip, [])

    # [中文]: 清理所有早于 (当前时间 - 窗口期) 的旧时间戳
    # [中文]: action_limit_config.window 是秒数
    valid_timestamps = [
        ts for ts in ip_timestamps if current_time - ts < action_limit_config.window
    ]

    if len(valid_timestamps) >= action_limit_config.limit:
        # [中文]: 已达到或超过限制
        _rate_limiter_logger.info(
            f"IP {client_ip} 的操作 '{action_type}' (用户类型: {limit_config_key}) 超出速率限制: "
            f"{len(valid_timestamps)} 次 >= {action_limit_config.limit} 次 / {action_limit_config.window} 秒。"
        )
        timestamps_dict_ref[client_ip] = (
            valid_timestamps  # [中文]: 更新为清理后的列表（可选）
        )
        return True  # [中文]: 应被限制

    # [中文]: 未超限，记录当前时间戳
    valid_timestamps.append(current_time)
    timestamps_dict_ref[client_ip] = valid_timestamps
    _rate_limiter_logger.debug(
        f"IP {client_ip} 的操作 '{action_type}' (用户类型: {limit_config_key}) 未超限。 "
        f"当前计数: {len(valid_timestamps)} / {action_limit_config.limit}。"
    )
    return False  # [中文]: 不限制


# endregion 速率限制核心逻辑区域结束

__all__ = [
    "is_rate_limited",
    # [中文]: # "rate_limit_dependency", # 这是一个概念性的、未实际使用的依赖项
    # [中文]: # 导出这些全局变量是为了可能的外部监控或管理，但通常不建议直接从其他模块修改它们
    "ip_exam_request_timestamps",
    "ip_auth_attempt_timestamps",
]

if __name__ == "__main__":
    # [中文]: 此模块不应作为主脚本执行。它定义了速率限制相关的函数和数据结构，应由其他模块导入和使用。
    _rate_limiter_logger.info(f"模块 {__name__} 提供了速率限制功能，不应直接执行。")
    print(
        f"模块 {__name__} 提供了速率限制功能，不应直接执行。"
    )

# region FastAPI 依赖项 (用于路由中直接应用速率限制) - 概念性
# [中文]: 注意：以下依赖项 `rate_limit_dependency` 是一个设计概念，
# [中文]: 在当前版本的应用中并未直接在路由上使用。
# [中文]: 实际的速率限制检查是通过在路由处理函数内部调用 `is_rate_limited` 来完成的。
# [中文]: 这是因为依赖项需要预先知道 `action_type` 和 `user_tags`，这使得通用依赖项难以实现，
# [中文]: 或者需要更复杂的依赖项链。


async def rate_limit_dependency(
    request: Request,
    action_type: str,  # [中文]: 需要在路由定义中通过某种方式传递此操作类型
    # [中文]: # user_tags: Optional[List[UserTag]] = Depends(get_current_user_tags_optional) # 示例：获取用户标签的依赖
):
    """
    一个通用的速率限制FastAPI依赖项（概念性演示）。

    实际使用时，可能需要为每个受限操作创建特定的依赖项，
    或者在路由函数内部调用 `is_rate_limited`（当前采用此方式）。
    """
    # [中文]: # # 示例实现逻辑:
    # [中文]: # client_ip = get_client_ip_from_request(request) # 使用项目中的工具函数获取IP
    # [中文]: # # 假设 user_tags 已通过另一个依赖项获取
    # [中文]: # current_user_tags: Optional[List[UserTag]] = getattr(request.state, "user_tags", None)

    # [中文]: # # 管理员通常不受速率限制
    # [中文]: # if current_user_tags and UserTag.ADMIN in current_user_tags:
    # [中文]: #     return

    # [中文]: # if is_rate_limited(client_ip, action_type, current_user_tags):
    # [中文]: #     _rate_limiter_logger.warning(f"请求被速率限制。IP: {client_ip}, 操作: {action_type}")
    # [中文]: #     raise HTTPException(
    # [中文]: #         status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
    # [中文]: #         detail=f"操作 '{action_type}' 请求过于频繁，请稍后再试。",
    # [中文]: #     )
    pass  # [中文]: 当前为空操作，实际限制在路由处理函数中完成


# endregion FastAPI 依赖项结束
