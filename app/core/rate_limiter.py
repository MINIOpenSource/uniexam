# region 模块导入
import time
from typing import Dict, List, Optional
import logging

from fastapi import Request, HTTPException, status as http_status

# 使用相对导入从同级目录的 config 模块导入 settings
from .config import settings
# 使用相对导入从同级目录的 security 模块导入 get_current_user_info_from_token (如果需要基于用户标签的速率限制)
# from .security import get_current_user_info_from_token # 暂时不直接依赖，由调用方传入user_info
from ..models.user_models import UserTag 
from ..utils.helpers import get_client_ip_from_request 

# endregion

# region 全局变量与初始化

# 获取本模块的logger实例
_rate_limiter_logger = logging.getLogger(__name__)

# 用于速率限制的数据结构:
# 键为IP地址 (str)，值为对应操作的请求时间戳列表 (List[float])
# 分开存储不同操作的速率限制数据
ip_exam_request_timestamps: Dict[str, List[float]] = {} # 获取新试卷
ip_auth_attempt_timestamps: Dict[str, List[float]] = {} # 登录/注册等认证尝试

# endregion

# region 速率限制核心逻辑

def is_rate_limited(
    client_ip: str,
    action_type: str, # 例如 "get_exam", "auth_attempts"
    user_tags: Optional[List[UserTag]] = None
) -> bool:
    """
    检查指定IP和操作类型是否超出速率限制。

    参数:
        client_ip: 客户端的IP地址。
        action_type: 操作类型，用于从配置中查找对应的限制规则。
        user_tags: (可选) 当前用户的标签列表，用于应用特定用户类型的限制。

    返回:
        True 如果请求应被限制，否则 False。
    """
    current_time = time.time()
    
    # 根据用户标签确定使用哪套速率限制规则
    # 默认为 "default_user"，如果用户有 "limited" 标签，则使用 "limited_user"
    # 管理员 (admin) 通常不受此速率限制 (在调用此函数前判断)
    limit_config_key = "default_user"
    if user_tags and UserTag.LIMITED in user_tags:
        limit_config_key = "limited_user"
    
    # 从 settings 中获取对应操作类型的速率限制配置
    user_type_limits = settings.rate_limits.get(limit_config_key)
    if not user_type_limits:
        _rate_limiter_logger.error(f"未找到用户类型 '{limit_config_key}' 的速率限制配置。")
        return False # 配置错误，默认不限制

    action_limit_config = getattr(user_type_limits, action_type, None)
    if not action_limit_config:
        _rate_limiter_logger.error(
            f"未在用户类型 '{limit_config_key}' 中找到操作 '{action_type}' 的速率限制配置。"
        )
        return False # 配置错误，默认不限制

    # 选择对应操作的时间戳字典
    if action_type == "get_exam":
        timestamps_dict_ref = ip_exam_request_timestamps
    elif action_type == "auth_attempts":
        timestamps_dict_ref = ip_auth_attempt_timestamps
    else:
        _rate_limiter_logger.warning(f"未知的速率限制操作类型: {action_type}。")
        return False # 未知类型，默认不限制

    ip_timestamps = timestamps_dict_ref.get(client_ip, [])
    
    # 清理所有早于 (当前时间 - 窗口期) 的旧时间戳
    # action_limit_config.window 是秒数
    valid_timestamps = [
        ts for ts in ip_timestamps if current_time - ts < action_limit_config.window
    ]
    
    if len(valid_timestamps) >= action_limit_config.limit:
        # 已达到或超过限制
        _rate_limiter_logger.info(
            f"IP {client_ip} 的操作 '{action_type}' (用户类型: {limit_config_key}) 超出速率限制: "
            f"{len(valid_timestamps)} 次 >= {action_limit_config.limit} 次 / {action_limit_config.window} 秒。"
        )
        timestamps_dict_ref[client_ip] = valid_timestamps # 更新为清理后的列表（可选）
        return True # 应被限制
    
    # 未超限，记录当前时间戳
    valid_timestamps.append(current_time)
    timestamps_dict_ref[client_ip] = valid_timestamps
    _rate_limiter_logger.debug(
        f"IP {client_ip} 的操作 '{action_type}' (用户类型: {limit_config_key}) 未超限。 "
        f"当前计数: {len(valid_timestamps)} / {action_limit_config.limit}。"
    )
    return False # 不限制

# endregion

# region FastAPI 依赖项 (用于路由中直接应用速率限制)

async def rate_limit_dependency(
    request: Request,
    action_type: str, # 需要在路由中指定此操作类型
    # user_info: Optional[Dict[str, Any]] = Depends(get_current_user_info_from_token_optional) # 可选的认证用户
    # 为了解耦，可以让路由函数自己获取用户信息并传入 is_rate_limited
    # 或者创建一个更复杂的依赖项，它首先获取用户信息，然后应用速率限制
):
    """
    一个通用的速率限制FastAPI依赖项（概念）。
    实际使用时，可能需要为每个受限操作创建特定的依赖项，
    或者在路由函数内部调用 is_rate_limited。

    这个通用依赖项的实现比较复杂，因为它需要知道 action_type 和 user_tags。
    更常见的做法是在每个需要速率限制的路由函数开头调用 is_rate_limited。
    """
    # client_ip = get_client_ip(request)
    # user_tags = user_info.get("tags") if user_info else None
    # if UserTag.ADMIN not in (user_tags or []): # 管理员不受限
    #     if is_rate_limited(client_ip, action_type, user_tags):
    #         raise HTTPException(
    #             status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
    #             detail=f"Rate limit exceeded for action: {action_type}",
    #         )
    pass # 暂时将此依赖项留空，具体限制在路由函数中实现

# endregion
