# -*- coding: utf-8 -*-
# region 模块导入与初始设置
"""
FastAPI 应用主入口文件。

负责初始化FastAPI应用实例，加载配置，设置中间件，
挂载各个功能模块的API路由 (用户认证、核心答题、WebSocket 通信、管理员接口等)，
并定义应用的生命周期事件 (启动和关闭时的任务)。
(This is the main entry point file for the FastAPI application.
 It is responsible for initializing the FastAPI app instance, loading configurations,
 setting up middleware, mounting API routers for various functional modules
 (user authentication, core exam-taking, WebSocket communication, admin interfaces, etc.),
 and defining application lifecycle events (tasks for startup and shutdown).)
"""

import asyncio
import logging  # 用于配置应用级日志
import os
from datetime import datetime  # For export filename timestamp
from typing import Any, Dict, List, Optional  # 确保导入 Dict, Any
from uuid import UUID

import uvicorn
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    status as http_status,
)
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

# --- 路由模块导入 ---
from .admin_routes import admin_router  # 管理员接口路由

# --- 核心模块导入 (使用相对路径) ---
from .core.config import (  # 全局配置和枚举
    DifficultyLevel,
    settings,
)
from .core.rate_limiter import is_rate_limited  # 速率限制检查函数
from .core.security import (  # 安全和认证相关
    UserTag,  # 用户标签枚举
    create_access_token,
    get_current_active_user_uid,  # 依赖注入函数，获取当前活跃用户UID
)

# --- CRUD 操作模块实例 ---
# 这些实例在 app.crud.__init__ 中创建并导出，方便统一管理
from .crud import (
    initialize_crud_instances,  # CRUD及存储库初始化函数
    paper_crud_instance,
    qb_crud_instance,
    repository_instance,
    user_crud_instance,
)
from .models.paper_models import (  # 试卷相关Pydantic模型
    ExamPaperResponse,
    GradingResultResponse,
    HistoryItem,
    HistoryPaperDetailResponse,
    PaperSubmissionPayload,
    UpdateProgressResponse,
)
from .models.qb_models import LibraryIndexItem  # 用于 /difficulties 接口的题库索引模型
from .models.token_models import (  # Token及认证状态相关Pydantic模型
    Token,
)

# --- Pydantic 模型导入 ---
from .models.user_models import (  # 用户相关Pydantic模型
    UserCreate,
    UserDirectoryEntry,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserPublicProfile,
)
from .services.audit_logger import audit_logger_service  # Audit logger
from .services.websocket_manager import websocket_manager  # WebSocket Manager

# --- 工具函数导入 ---
from .utils.export_utils import data_to_csv, data_to_xlsx  # Export utilities
from .utils.helpers import (  # 工具函数
    format_short_uuid,
    get_client_ip_from_request,
    get_current_timestamp_str,
)
from .websocket_routes import ws_router  # WebSocket 接口路由

# endregion

__all__ = [
    "app",
    "startup_event",
    "shutdown_event",
]
# %%
# region 应用级日志记录器配置
# 日志记录现在由 core.config 中的 setup_logging 函数在加载 settings 时配置。
# 这里我们仍然可以获取一个特定于此模块的日志记录器实例。
app_logger = logging.getLogger(__name__)
# endregion

# region FastAPI 应用实例与全局变量初始化
app = FastAPI(  # FastAPI 应用实例
    title=settings.app_name,  # 应用名称，来自配置
    description="在线考试系统API服务，提供用户账户管理、Token认证、试卷答题、题库管理以及管理员后台等功能。",  # 应用描述
    version="3.0.0",  # 应用版本
    # openapi_url="/api/v1/openapi.json" # 自定义OpenAPI路径 (可选)
)

# CRUD 实例已在顶部导入，并将在 startup_event 中被初始化。

# endregion

# region FastAPI 生命周期事件 (Startup & Shutdown)


async def main_periodic_tasks():
    """
    运行所有主要的定期后台任务。
    此函数在应用启动时通过 `asyncio.create_task` 启动，
    它内部会异步地启动各个具体的周期性任务，例如Token清理。
    （Cloudflare IP更新任务当前已注释掉）
    """
    # Cloudflare IP 更新任务 (当前注释掉)
    # async def periodic_cloudflare_ip_update():
    #     """定期从Cloudflare获取并更新IP地址范围。"""
    #     from .utils.helpers import fetch_and_update_cloudflare_ips_once # 延迟导入
    #     while True:
    #         _task_logger = logging.getLogger(__name__ + ".periodic_cloudflare_ip_update")
    #         try:
    #             _task_logger.info("尝试更新Cloudflare IP地址范围...")
    #             await fetch_and_update_cloudflare_ips_once()
    #             _task_logger.info("Cloudflare IP地址范围已更新。")
    #         except Exception as e_cf:
    #             _task_logger.error(f"更新Cloudflare IP时发生错误: {e_cf}", exc_info=True)
    #         await asyncio.sleep(settings.cloudflare_ips.fetch_interval_seconds)

    # Token清理任务
    async def periodic_token_cleanup_task():
        """定期清理过期的用户访问Token。"""
        _task_logger = logging.getLogger(__name__ + ".periodic_token_cleanup_task")
        while True:
            # 使用与旧DB持久化任务相同的间隔时间，可按需调整
            await asyncio.sleep(settings.db_persist_interval_seconds)
            _task_logger.debug(
                f"开始定期清理过期Token (每 {settings.db_persist_interval_seconds} 秒)..."
            )
            if user_crud_instance and hasattr(
                user_crud_instance, "cleanup_expired_tokens"
            ):
                try:
                    await user_crud_instance.cleanup_expired_tokens()
                except Exception as e_token_cleanup:
                    _task_logger.error(
                        f"清理过期Token时发生错误: {e_token_cleanup}", exc_info=True
                    )
            else:
                _task_logger.warning(
                    "user_crud_instance 不可用或没有 cleanup_expired_tokens 方法。"
                )

    # 创建并启动所有主要的后台任务
    # asyncio.create_task(periodic_cloudflare_ip_update()) # Cloudflare IP更新任务启动点
    # app_logger.info("Cloudflare IP 定期更新任务已计划。")

    asyncio.create_task(periodic_token_cleanup_task())
    app_logger.info("过期Token定期清理任务已计划。")


@app.on_event("startup")
async def startup_event():
    """
    应用启动时执行的异步事件处理器。
    负责初始化CRUD实例、数据库连接（通过repository）、以及启动后台周期性任务。
    """
    app_logger.info("应用启动事件：开始执行启动任务...")

    # 初始化CRUD实例和存储库 (包括数据库连接和表结构检查/创建)
    await initialize_crud_instances()
    app_logger.info("CRUD实例和存储库已成功初始化。")

    # 启动后台周期性任务
    asyncio.create_task(main_periodic_tasks())
    app_logger.info("后台周期性任务已启动。")
    app_logger.info("应用启动任务完成。")


@app.on_event("shutdown")
async def shutdown_event():
    """
    应用关闭时执行的异步事件处理器。
    负责执行数据持久化（通过repository）和断开数据库连接等清理工作。
    """
    app_logger.info("应用关闭事件：开始执行关闭任务...")

    if repository_instance:
        app_logger.info("正在持久化所有通过存储库管理的数据...")
        try:
            # 对于JSON或文件型存储, 此方法会将内存数据写入文件。
            # 对于SQL数据库, 数据通常实时写入, 此方法可能为空操作或执行最终同步。
            await repository_instance.persist_all_data()
            app_logger.info("所有存储库数据已成功持久化。")
        except Exception as e_persist:
            app_logger.error(f"关闭时持久化数据失败: {e_persist}", exc_info=True)

        app_logger.info("正在断开与数据存储的连接...")
        try:
            await repository_instance.disconnect()
            app_logger.info("数据存储连接已成功断开。")
        except Exception as e_disconnect:
            app_logger.error(
                f"关闭时断开数据存储连接失败: {e_disconnect}", exc_info=True
            )
    else:
        app_logger.warning(
            "Repository实例未初始化，无法执行标准的数据持久化或断开连接操作。"
        )

    app_logger.info("应用关闭任务完成。")


# endregion

# region FastAPI 中间件 (例如 CORS)
# CORS (跨源资源共享) 中间件，允许特定来源的前端应用访问API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[  # 允许的来源列表
        settings.frontend_domain,  # 从配置读取前端域名
        "http://localhost",  # 本地开发常见端口
        "http://127.0.0.1",  # 本地开发常见IP
    ],
    allow_credentials=True,  # 是否允许携带凭证 (如 cookies)
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有HTTP请求头
)
# endregion

# region 用户认证 API 端点
auth_router = APIRouter(tags=["用户认证 (User Authentication)"])


@auth_router.post(
    "/signin",  # 路径：POST /auth/signin
    response_model=Token,  # 成功响应模型
    status_code=http_status.HTTP_201_CREATED,  # 成功状态码：201 Created
    summary="用户注册",
    description="新用户通过提供用户名、密码等信息进行注册。成功后返回访问令牌。",
    responses={
        http_status.HTTP_409_CONFLICT: {"description": "用户名已存在"},
        http_status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "请求数据验证失败"},
        http_status.HTTP_429_TOO_MANY_REQUESTS: {"description": "请求过于频繁"},
    },
)
async def sign_up_new_user(payload: UserCreate, request: Request):
    """
    用户注册接口。

    接收用户提交的注册信息（如用户名 `uid`、密码 `password`、昵称 `nickname` 等）。
    如果用户名未被占用且提供的数据有效，系统将创建新用户，并返回一个访问令牌 (`Token`) 用于后续认证。

    - **成功**: 返回 `201 Created` 状态码及 `Token` 对象。
    - **失败 (用户名已存在)**: 返回 `409 Conflict` 状态码及错误详情。
    - **失败 (请求数据无效)**: 返回 `422 Unprocessable Entity` 状态码及Pydantic验证错误详情。
    - **失败 (请求频繁)**: 返回 `429 Too Many Requests` 状态码。
    """
    client_ip = get_client_ip_from_request(request)
    if is_rate_limited(client_ip, "auth_attempts"):
        app_logger.warning(f"用户注册请求过于频繁 (IP: {client_ip})。")
        # Audit log for rate limit
        await audit_logger_service.log_event(
            action_type="USER_REGISTER",
            status="FAILURE",
            actor_ip=client_ip,
            details={"message": "注册请求过于频繁", "target_resource_id": payload.uid},
        )
        raise HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail="注册请求过于频繁，请稍后再试。",
        )

    user = await user_crud_instance.create_user(payload)
    if not user:
        app_logger.warning(
            f"用户注册失败：用户名 '{payload.uid}' 已存在 (IP: {client_ip})。"
        )
        # Audit log for registration failure (user exists)
        await audit_logger_service.log_event(
            action_type="USER_REGISTER",
            status="FAILURE",
            actor_uid=payload.uid,
            actor_ip=client_ip,
            details={"message": "用户名已存在"},
        )
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"用户名 '{payload.uid}' 已被注册。",
        )

    token_str = await create_access_token(user.uid, user.tags)
    app_logger.info(f"新用户 '{payload.uid}' 注册成功并登录 (IP: {client_ip})。")
    # Audit log for successful registration
    await audit_logger_service.log_event(
        action_type="USER_REGISTER",
        status="SUCCESS",
        actor_uid=user.uid,
        actor_ip=client_ip,
        details={"message": "新用户注册成功"},
    )
    return Token(access_token=token_str)  # 返回Token


@auth_router.post(
    "/login",  # 路径：POST /auth/login
    response_model=Token,  # 成功响应模型
    summary="用户登录",
    description="用户通过提供用户名和密码进行登录。成功后返回访问令牌。",
    responses={
        http_status.HTTP_401_UNAUTHORIZED: {"description": "用户名或密码错误"},
        http_status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "请求数据验证失败"},
        http_status.HTTP_429_TOO_MANY_REQUESTS: {"description": "请求过于频繁"},
    },
)
async def login_for_access_token(payload: UserCreate, request: Request):
    """
    用户登录接口。

    接收用户提交的登录凭证（用户名 `uid` 和密码 `password`）。
    如果凭证有效，系统将返回一个访问令牌 (`Token`) 用于后续认证。

    - **成功**: 返回 `200 OK` 状态码及 `Token` 对象。
    - **失败 (凭证错误)**: 返回 `401 Unauthorized` 状态码及错误详情。
    - **失败 (请求数据无效)**: 返回 `422 Unprocessable Entity` 状态码及Pydantic验证错误详情。
    - **失败 (请求频繁)**: 返回 `429 Too Many Requests` 状态码。
    """
    client_ip = get_client_ip_from_request(request)
    if is_rate_limited(client_ip, "auth_attempts"):
        app_logger.warning(f"用户登录请求过于频繁 (IP: {client_ip})。")
        # Audit log for rate limit
        await audit_logger_service.log_event(
            action_type="USER_LOGIN",
            status="FAILURE",
            actor_ip=client_ip,
            details={
                "message": "登录请求过于频繁",
                "target_resource_id": payload.uid if payload else "N/A",
            },
        )
        raise HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录请求过于频繁，请稍后再试。",
        )

    from .core.security import verify_password

    user = await user_crud_instance.get_user_by_uid(payload.uid)
    if not user or not verify_password(payload.password, user.hashed_password):
        app_logger.warning(
            f"用户 '{payload.uid}' 登录失败：用户名或密码错误 (IP: {client_ip})。"
        )
        # Audit log for login failure
        await audit_logger_service.log_event(
            action_type="USER_LOGIN",
            status="FAILURE",
            actor_uid=payload.uid,
            actor_ip=client_ip,
            details={"message": "用户名或密码错误"},
        )
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码不正确。",
        )

    token_str = await create_access_token(user.uid, user.tags)
    app_logger.info(f"用户 '{payload.uid}' 登录成功 (IP: {client_ip})。")
    # Audit log for successful login
    await audit_logger_service.log_event(
        action_type="USER_LOGIN",
        status="SUCCESS",
        actor_uid=user.uid,
        actor_ip=client_ip,
        details={"message": "用户登录成功"},
    )
    return Token(access_token=token_str)


@auth_router.get(
    "/login",  # 路径: GET /auth/login?token={old_token}
    response_model=Token,
    summary="刷新访问令牌",
    description="使用一个有效的旧访问令牌获取一个新的访问令牌。成功后，旧令牌将失效。",
    responses={
        http_status.HTTP_401_UNAUTHORIZED: {"description": "提供的旧令牌无效或已过期"}
    },
)
async def refresh_access_token(
    token_to_refresh: str = Query(
        ..., alias="token", description="待刷新的有效旧访问令牌"
    ),
):
    """
    刷新访问令牌接口。

    通过查询参数 `token` 接收一个有效的旧访问令牌。
    如果旧令牌有效，系统将使其失效，并签发一个新的访问令牌。

    - **成功**: 返回 `200 OK` 状态码及新的 `Token` 对象。
    - **失败 (旧令牌无效/过期)**: 返回 `401 Unauthorized` 状态码及错误详情。
    """
    from .core.security import (
        invalidate_token,
        validate_token_and_get_user_info,
    )

    user_info = await validate_token_and_get_user_info(token_to_refresh)
    if not user_info:
        app_logger.warning(
            f"刷新令牌失败：提供的旧令牌无效或已过期 (部分令牌: {token_to_refresh[:8]}...)"
        )
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="提供的令牌无效或已过期，无法刷新。",
        )

    await invalidate_token(token_to_refresh)
    new_token_str = await create_access_token(
        user_info["user_uid"], user_info["tags"]
    )  # 创建新Token

    app_logger.info(
        f"用户 '{user_info['user_uid']}' 的Token (部分旧Token: {token_to_refresh[:8]}...) 已成功刷新。"
    )
    return Token(access_token=new_token_str)


app.include_router(auth_router, prefix="/auth")  # 挂载认证路由，统一前缀 /auth
# endregion

# region 用户个人信息管理 API 端点
user_profile_router = APIRouter(
    prefix="/users/me",  # 路由前缀 /users/me
    tags=["用户个人资料 (User Profile)"],  # API文档标签
    dependencies=[
        Depends(get_current_active_user_uid)
    ],  # 所有接口都需要有效Token进行认证
)


@user_profile_router.get(
    "",
    response_model=UserPublicProfile,
    summary="获取当前用户信息",
    description="获取当前认证用户的公开个人资料，包括UID、昵称、邮箱、QQ以及用户标签等信息。",
    responses={
        http_status.HTTP_401_UNAUTHORIZED: {"description": "令牌无效或已过期"},
        http_status.HTTP_403_FORBIDDEN: {"description": "用户账户已被封禁"},
        http_status.HTTP_404_NOT_FOUND: {"description": "用户未找到"},
    },
)
async def read_users_me(current_user_uid: str = Depends(get_current_active_user_uid)):
    """
    获取当前用户的公开个人资料。

    此端点需要有效的用户认证（通过Token）。
    成功时返回用户的公开信息，不包括密码等敏感数据。

    - **成功**: 返回 `200 OK` 及 `UserPublicProfile` 模型。
    - **失败 (认证问题)**: 可能返回 `401 Unauthorized` 或 `403 Forbidden`。
    - **失败 (用户不存在)**: 返回 `404 Not Found` (理论上在Token有效时不应发生)。
    """
    user = await user_crud_instance.get_user_by_uid(current_user_uid)
    if not user:
        # 理论上不应发生，因为Token验证时用户应该存在于数据库中
        app_logger.error(
            f"获取当前用户信息失败：用户 '{current_user_uid}' 在数据库中未找到，但Token有效。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    # 从数据库模型 (UserInDB) 转换为公开的模型 (UserPublicProfile)
    return UserPublicProfile.model_validate(user)


@user_profile_router.put(
    "",
    response_model=UserPublicProfile,
    summary="更新当前用户个人资料",
    description="允许当前认证用户更新其个人资料，如昵称、邮箱或QQ号码。请求体中应包含待更新的字段及其新值。",
    responses={
        http_status.HTTP_401_UNAUTHORIZED: {"description": "令牌无效或已过期"},
        http_status.HTTP_403_FORBIDDEN: {"description": "用户账户已被封禁"},
        http_status.HTTP_404_NOT_FOUND: {"description": "用户未找到或更新数据无效"},
        http_status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "请求体验证失败"},
    },
)
async def update_users_me(
    profile_data: UserProfileUpdate,
    current_user_uid: str = Depends(get_current_active_user_uid),
):
    """
    更新当前用户的个人资料。

    用户可以更新自己的昵称、邮箱或QQ号。
    只有在请求体中提供的字段才会被尝试更新。

    - **成功**: 返回 `200 OK` 及更新后的 `UserPublicProfile` 模型。
    - **失败 (用户不存在或更新无效)**: 返回 `404 Not Found`。
    - **失败 (认证问题)**: 可能返回 `401 Unauthorized` 或 `403 Forbidden`。
    - **失败 (请求体验证问题)**: 返回 `422 Unprocessable Entity`。
    """
    updated_user = await user_crud_instance.update_user_profile(
        current_user_uid, profile_data
    )
    if not updated_user:
        app_logger.warning(
            f"用户 '{current_user_uid}' 更新个人资料失败（可能用户不存在或数据无效）。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="User not found or update data invalid.",
        )
    return UserPublicProfile.model_validate(updated_user)


@user_profile_router.put(
    "/password",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="修改当前用户密码",
    description="允许当前认证用户修改自己的密码。请求体中必须提供当前密码和新密码。",
    responses={
        http_status.HTTP_400_BAD_REQUEST: {"description": "当前密码不正确"},
        http_status.HTTP_401_UNAUTHORIZED: {"description": "令牌无效或已过期"},
        http_status.HTTP_403_FORBIDDEN: {"description": "用户账户已被封禁"},
        http_status.HTTP_404_NOT_FOUND: {"description": "用户未找到"},
        http_status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "请求体验证失败 (例如新密码不符合要求)"
        },
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "更新密码时发生未知错误"
        },
    },
)
async def update_users_me_password(
    password_data: UserPasswordUpdate,
    current_user_uid: str = Depends(get_current_active_user_uid),
):
    """
    当前认证用户修改自己的密码。

    需要提供当前密码进行验证，以及符合复杂度要求的新密码。
    成功修改密码后，建议用户使用新密码重新登录。

    - **成功**: 返回 `204 No Content`。
    - **失败 (当前密码错误)**: 返回 `400 Bad Request`。
    - **失败 (用户不存在)**: 返回 `404 Not Found`。
    - **失败 (认证问题)**: 可能返回 `401 Unauthorized` 或 `403 Forbidden`。
    - **失败 (请求体验证问题)**: 返回 `422 Unprocessable Entity`。
    - **失败 (服务器内部错误)**: 返回 `500 Internal Server Error`。
    """
    from .core.security import get_password_hash, verify_password

    user_in_db = await user_crud_instance.get_user_by_uid(current_user_uid)
    if not user_in_db:  # 理论上不应发生
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="User not found."
        )

    # 验证当前密码是否正确
    if not verify_password(password_data.current_password, user_in_db.hashed_password):
        app_logger.warning(f"用户 '{current_user_uid}' 修改密码失败：当前密码不正确。")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password.",
        )

    # 对新密码进行哈希处理并更新到数据库
    new_hashed_password = get_password_hash(password_data.new_password)
    success = await user_crud_instance.update_user_password(
        current_user_uid, new_hashed_password
    )
    if not success:  # 理论上如果用户存在，这里应该总是成功
        app_logger.error(f"用户 '{current_user_uid}' 修改密码时发生未知错误。")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password.",
        )

    app_logger.info(f"用户 '{current_user_uid}' 成功修改密码。")
    # 成功修改密码后，可以考虑让用户所有旧Token失效，但这需要更复杂的Token管理机制
    return  # HTTP 204 不需要响应体


app.include_router(user_profile_router)  # 挂载用户个人资料路由
# endregion

# region 核心答题 API 端点
exam_router = APIRouter(
    dependencies=[Depends(get_current_active_user_uid)],  # 所有接口都需要有效Token
    tags=["核心答题 (Exam Taking)"],
)


@exam_router.get(
    "/get_exam",
    response_model=ExamPaperResponse,
    summary="请求新试卷",
    description="为当前认证用户创建一份指定难度（可选题目数量）的新试卷。返回试卷的详细信息，包括题目列表。非管理员用户受速率限制。",
    responses={
        http_status.HTTP_200_OK: {"description": "成功获取新试卷"},
        http_status.HTTP_400_BAD_REQUEST: {
            "description": "请求参数无效或业务逻辑错误（如题库题目不足）"
        },
        http_status.HTTP_401_UNAUTHORIZED: {"description": "令牌无效或已过期"},
        http_status.HTTP_403_FORBIDDEN: {"description": "用户账户已被封禁"},
        http_status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "获取新试卷请求过于频繁"
        },
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "创建新试卷时发生意外服务器错误"
        },
    },
)
async def request_new_exam_paper(
    request: Request,
    current_user_uid: str = Depends(get_current_active_user_uid),
    difficulty: DifficultyLevel = Query(
        default=DifficultyLevel.hybrid,
        description="新试卷的难度级别 (例如: easy, hybrid, hard)",
    ),
    num_questions: Optional[int] = Query(
        None,
        ge=1,  # 最小题目数为1
        le=200,  # 假设最大题目数限制为200
        description="请求的题目数量 (可选, 若提供则覆盖该难度默认题量)",
    ),
):
    """
    为认证用户创建一份指定难度和（可选）指定题目数量的新试卷。
    返回试卷ID、难度及题目列表（题目已打乱选项顺序）。
    非管理员用户受速率限制。
    """
    from .core.security import validate_token_and_get_user_info  # 延迟导入

    client_ip = get_client_ip_from_request(request)
    timestamp_str = get_current_timestamp_str()  # 获取当前时间戳字符串用于日志

    # 检查用户标签，管理员不受速率限制
    # 需要重新从Token获取用户信息以检查标签，因为依赖注入的UID不包含标签信息
    user_info = await validate_token_and_get_user_info(
        request.query_params.get("token", "")  # 从请求参数中获取Token
    )
    user_tags = user_info.get("tags", []) if user_info else []

    if UserTag.ADMIN not in user_tags:  # 如果用户不是管理员
        if is_rate_limited(client_ip, "get_exam", user_tags):  # 检查速率限制
            app_logger.info(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}, 标签: {[t.value for t in user_tags]}) 请求新试卷，但超出速率限制。"
            )
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests for new exam.",
            )

    app_logger.info(
        f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 请求一份新的 [{difficulty.value}] 试卷 (题量: {num_questions or '默认'})。"
    )
    try:
        # 调用 PaperCRUD 创建新试卷
        new_paper_client_data = await paper_crud_instance.create_new_paper(
            request=request,
            user_uid=current_user_uid,
            difficulty=difficulty,
            num_questions_override=num_questions,
        )
        short_id = format_short_uuid(
            new_paper_client_data["paper_id"]
        )  # 格式化UUID用于日志
        app_logger.info(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 成功创建新试卷 [{difficulty.value}]：{short_id}"
        )
        # 构造并返回响应
        response = ExamPaperResponse(
            paper_id=new_paper_client_data["paper_id"],
            difficulty=new_paper_client_data["difficulty"],
            paper=new_paper_client_data["paper"],
        )
        # WebSocket 广播: 考试开始
        ws_message_started = {
            "event_type": "EXAM_STARTED",
            "user_uid": current_user_uid,
            "paper_id": str(new_paper_client_data["paper_id"]),
            "difficulty": new_paper_client_data["difficulty"].value,
            "num_questions": len(new_paper_client_data["paper"]),
            "message": f"用户 {current_user_uid} 开始了新试卷 {str(new_paper_client_data['paper_id'])} (难度: {new_paper_client_data['difficulty'].value})。",
        }
        await websocket_manager.broadcast_message(ws_message_started)
        return response
    except ValueError as ve:  # 例如题库题目不足或难度无效
        app_logger.warning(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 创建新试卷失败 (业务逻辑错误): {ve}"
        )
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(ve)
        ) from ve
    except Exception as e:  # 其他意外错误
        app_logger.error(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 创建新试卷时发生意外错误: {e}",
            exc_info=True,  # 记录异常堆栈信息
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating new exam: {str(e)}",
        ) from e


@exam_router.post(
    "/update",
    response_model=UpdateProgressResponse,
    summary="更新答题进度",
    description="用户提交一部分答案以保存当前答题进度。此接口不进行批改，仅保存用户答案。",
    responses={
        http_status.HTTP_200_OK: {
            "model": UpdateProgressResponse,
            "description": "进度已成功保存",
        },
        http_status.HTTP_400_BAD_REQUEST: {
            "description": "请求数据无效（如答案数量错误）"
        },
        http_status.HTTP_403_FORBIDDEN: {"description": "试卷已完成，无法更新进度"},
        http_status.HTTP_404_NOT_FOUND: {"description": "试卷未找到或用户无权访问"},
        # 401 Unauthorized is inherited from router dependencies
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "服务器内部错误"},
    },
)
async def update_exam_progress(
    payload: PaperSubmissionPayload,
    request: Request,
    current_user_uid: str = Depends(get_current_active_user_uid),
):
    """
    更新用户未完成试卷的答题进度。

    - **成功**: 返回 `200 OK` 及 `UpdateProgressResponse` 对象。
    - **失败 (未找到或无权限)**: 引发 `HTTPException` 状态码 `404 Not Found`。
    - **失败 (试卷已完成)**: 引发 `HTTPException` 状态码 `403 Forbidden`。
    - **失败 (答案数量错误)**: 引发 `HTTPException` 状态码 `400 Bad Request`。
    - **失败 (其他错误)**: 引发 `HTTPException` 状态码 `400 Bad Request` 或 `500 Internal Server Error`。
    """
    client_ip = get_client_ip_from_request(request)
    timestamp_str = get_current_timestamp_str()
    short_paper_id = format_short_uuid(payload.paper_id)
    app_logger.info(
        f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 正在更新试卷 {short_paper_id} 的进度。"
    )

    try:
        update_result = await paper_crud_instance.update_paper_progress(
            payload.paper_id, current_user_uid, payload.result, request
        )
        status_code_text = update_result.get("status_code")
        message = update_result.get("message", "处理更新时发生未知错误。")

        if status_code_text == "PROGRESS_SAVED":
            app_logger.info(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 成功保存试卷 {short_paper_id} 进度。"
            )
            # WebSocket 广播: 考试进度更新
            ws_message_progress = {
                "event_type": "EXAM_PROGRESS_UPDATE",
                "user_uid": current_user_uid,
                "paper_id": str(payload.paper_id),
                "num_answered": len(
                    payload.result
                ),  # 注意: payload.result 是当前提交的答案，不一定是总答题数
                # update_result 可能包含更准确的总答题数字段
                "message": f"用户 {current_user_uid} 更新了试卷 {short_paper_id} 的进度。",
            }
            # 如果 update_result 包含更准确的已回答问题数, 例如:
            # if "answered_count" in update_result:
            #    ws_message_progress["num_answered"] = update_result["answered_count"]
            await websocket_manager.broadcast_message(ws_message_progress)

            # 移除旧的自定义 'code' 字段，因为HTTP状态码现在是主要指标
            update_result.pop("code", None)
            return UpdateProgressResponse(**update_result)
        elif status_code_text == "NOT_FOUND":
            app_logger.warning(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度失败：{message}"
            )
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail=message
            )
        elif status_code_text == "ALREADY_COMPLETED":
            app_logger.warning(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度失败：{message}"
            )
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN, detail=message
            )
        elif status_code_text == "INVALID_ANSWERS_LENGTH":
            app_logger.warning(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度失败：{message}"
            )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST, detail=message
            )
        else:  # 其他业务逻辑错误
            app_logger.error(
                f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度时发生已知错误: {message}, 完整结果: {update_result}"
            )
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST, detail=message
            )  # 或者500，取决于错误的性质
    except HTTPException:  # 直接重新抛出已处理的HTTPException
        raise
    except Exception as e:  # 捕获未预期的错误
        app_logger.error(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度时发生意外错误: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新进度时发生意外服务器错误。",
        ) from e


@exam_router.post(
    "/finish",  # 路径: POST /finish
    response_model=GradingResultResponse,
    summary="提交试卷答案进行批改",
)
async def submit_exam_paper(
    payload: PaperSubmissionPayload,  # 请求体包含试卷ID和用户答案
    request: Request,
    current_user_uid: str = Depends(get_current_active_user_uid),
):
    """
    提交用户已完成的试卷答案以进行批改。
    返回批改结果，包括得分、通过状态和可能的通行码。
    """
    client_ip = get_client_ip_from_request(request)
    timestamp_str = get_current_timestamp_str()
    short_paper_id = format_short_uuid(payload.paper_id)
    app_logger.info(
        f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 正在提交试卷 {short_paper_id} 进行批改。"
    )
    try:
        # 调用 PaperCRUD 批改试卷
        outcome = await paper_crud_instance.grade_paper_submission(
            payload.paper_id, current_user_uid, payload.result, request
        )
        response_data = GradingResultResponse(**outcome)  # 将结果转换为响应模型

        # 记录详细的批改日志
        score, status_text = response_data.score, outcome.get("status_code")
        log_msg_prefix = f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 提交试卷 {short_paper_id} 的答案"
        if status_text == "PASSED":
            app_logger.info(
                f"{log_msg_prefix}，获得 {score if score is not None else 'N/A'} 分 ({response_data.score_percentage}%)，通过考试，入群码：{response_data.passcode or 'N/A'}"
            )
        elif status_text == "FAILED":
            app_logger.info(
                f"{log_msg_prefix}，获得 {score if score is not None else 'N/A'} 分 ({response_data.score_percentage}%)，未能通过考试"
            )
        # ... 其他状态的日志记录 ...
        else:
            app_logger.warning(
                f"{log_msg_prefix}，结果: {status_text}, 详情: {outcome}"
            )
        # 返回包含批改结果的JSON响应
        json_response = JSONResponse(
            content=response_data.model_dump(exclude_none=True), status_code=200
        )
        # WebSocket 广播: 考试提交
        ws_message_submitted = {
            "event_type": "EXAM_SUBMITTED",
            "user_uid": current_user_uid,
            "paper_id": str(payload.paper_id),
            "score": response_data.score,
            "score_percentage": response_data.score_percentage,
            "pass_status": outcome.get("status_code")
            == "PASSED",  # 使用原始 outcome 的 status_code
            "message": f"用户 {current_user_uid} 提交了试卷 {short_paper_id}，得分: {response_data.score if response_data.score is not None else 'N/A'}",
        }
        await websocket_manager.broadcast_message(ws_message_submitted)
        return json_response
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        app_logger.error(
            f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 提交试卷 {short_paper_id} 时发生意外服务器错误: {e}",
            exc_info=True,
        )
        error_detail = {  # 构造标准错误响应体
            "code": 500,
            "status_code": "SERVER_ERROR",
            "message": f"Error processing submission: {str(e)}",
        }
        return JSONResponse(content=error_detail, status_code=500)


@exam_router.get(
    "/history",
    # response_model=List[HistoryItem], # Conditional return
    summary="获取用户答题历史 (支持CSV/XLSX导出)",
    description="获取当前认证用户的简要答题历史记录列表。可通过 'format' 查询参数导出为 CSV 或 XLSX 文件。",
    responses={
        http_status.HTTP_200_OK: {
            "description": "成功获取答题历史 (JSON, CSV, or XLSX)"
        },
        http_status.HTTP_401_UNAUTHORIZED: {"description": "令牌无效或已过期"},
    },
)
async def get_user_exam_history(
    current_user_uid: str = Depends(get_current_active_user_uid),
    export_format: Optional[str] = Query(
        None, description="导出格式 (csv 或 xlsx)", alias="format", regex="^(csv|xlsx)$"
    ),
):
    """获取当前认证用户的简要答题历史记录列表 (试卷ID, 难度, 得分等)。支持导出。"""
    timestamp_str = get_current_timestamp_str()
    app_logger.info(
        f"[{timestamp_str}] 用户 '{current_user_uid}' 请求答题历史记录 (格式: {export_format or 'json'})。"
    )

    history_data = await paper_crud_instance.get_user_history(
        current_user_uid
    )  # This returns List[Dict]

    if export_format:
        if not history_data:
            app_logger.info(
                f"[{timestamp_str}] 用户 '{current_user_uid}' 没有答题历史数据可导出。"
            )
            # Return empty file for export

        data_to_export: List[Dict[str, Any]] = []
        for item in history_data:  # item is a dict
            pass_status_str = (
                "未完成"  # Default if no pass_status or status is not 'completed'
            )
            if (
                item.get("status") == "completed"
            ):  # Assuming 'status' field indicates completion
                if item.get("pass_status") is True:
                    pass_status_str = "通过"
                elif item.get("pass_status") is False:
                    pass_status_str = "未通过"

            difficulty_val = item.get("difficulty", "")
            difficulty_str = (
                difficulty_val.value
                if isinstance(difficulty_val, DifficultyLevel)
                else str(difficulty_val)
            )

            data_to_export.append(
                {
                    "试卷ID": str(item.get("paper_id", "")),
                    "难度": difficulty_str,
                    "状态": str(
                        item.get("status", "")
                    ),  # Assuming status is an enum or string
                    "总得分": item.get("total_score_obtained", ""),
                    "百分制得分": (
                        f"{item.get('score_percentage'):.2f}"
                        if item.get("score_percentage") is not None
                        else ""
                    ),
                    "通过状态": pass_status_str,
                    "提交时间": (
                        item.get("submission_time").strftime("%Y-%m-%d %H:%M:%S")
                        if item.get("submission_time")
                        else ""
                    ),
                }
            )

        headers = [
            "试卷ID",
            "难度",
            "状态",
            "总得分",
            "百分制得分",
            "通过状态",
            "提交时间",
        ]
        current_time_for_file = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = (
            f"答题历史_{current_user_uid}_{current_time_for_file}.{export_format}"
        )

        if export_format == "csv":
            app_logger.info(
                f"[{timestamp_str}] 用户 '{current_user_uid}' 准备导出答题历史到 CSV 文件: {filename}"
            )
            return data_to_csv(
                data_list=data_to_export, headers=headers, filename=filename
            )
        elif export_format == "xlsx":
            app_logger.info(
                f"[{timestamp_str}] 用户 '{current_user_uid}' 准备导出答题历史到 XLSX 文件: {filename}"
            )
            return data_to_xlsx(
                data_list=data_to_export, headers=headers, filename=filename
            )

    # Default JSON response
    if not history_data:
        app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' 答题历史为空。")
        # Return empty list, which is fine.

    return [HistoryItem(**item) for item in history_data]


@exam_router.get(
    "/history_paper",
    response_model=HistoryPaperDetailResponse,
    summary="获取指定历史试卷详情",
    description="用户获取自己答题历史中某一份特定试卷的详细题目、作答情况和批改结果（如果已批改）。",
    responses={
        http_status.HTTP_200_OK: {
            "model": HistoryPaperDetailResponse,
            "description": "成功获取历史试卷详情",
        },  # 添加model到成功响应
        http_status.HTTP_401_UNAUTHORIZED: {"description": "令牌无效或已过期"},
        http_status.HTTP_404_NOT_FOUND: {
            "description": "指定的历史试卷未找到或用户无权查看"
        },
    },
)
async def get_user_history_paper_detail(
    paper_id: UUID = Query(..., description="要获取详情的历史试卷ID"),
    current_user_uid: str = Depends(get_current_active_user_uid),
):
    """获取用户某次历史答题的详细情况，包括题目、用户答案等。"""
    timestamp_str = get_current_timestamp_str()
    short_paper_id = format_short_uuid(paper_id)
    app_logger.info(
        f"[{timestamp_str}] 用户 '{current_user_uid}' 请求历史试卷 {short_paper_id} 的详情。"
    )
    paper_detail = await paper_crud_instance.get_user_paper_detail_for_history(
        str(paper_id), current_user_uid
    )
    if not paper_detail:  # 如果未找到试卷或用户无权查看
        app_logger.warning(
            f"[{timestamp_str}] 用户 '{current_user_uid}' 请求的历史试卷 {short_paper_id} 未找到或无权限查看。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="指定的历史试卷未找到或您无权查看。",  # 确保detail为中文
        )
    return HistoryPaperDetailResponse(**paper_detail)


app.include_router(exam_router)  # 挂载核心答题路由
# endregion


# region 题库元数据接口 (公开，无需Token)
@app.get(
    "/difficulties",
    response_model=List[LibraryIndexItem],
    summary="获取可用题库难度列表",
    description="公开接口，返回系统中所有已定义的题库难度级别及其元数据（如名称、描述、默认题量等）。此接口无需认证。",
    tags=["公共接口 (Public)"],
    responses={
        http_status.HTTP_200_OK: {
            "model": List[LibraryIndexItem],
            "description": "成功获取题库难度列表",
        },  # 添加model到成功响应
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "获取题库元数据时发生服务器内部错误"
        },
    },
)
async def get_available_difficulties():
    """
    获取系统中所有已定义的题库难度及其元数据信息。
    这些信息通常从持久化存储中读取。
    此接口公开，无需认证。
    """
    timestamp_str = get_current_timestamp_str()
    app_logger.info(f"[{timestamp_str}] 公开接口：请求可用题库难度列表。")
    try:
        metadatas = await qb_crud_instance.get_all_library_metadatas()
        if not metadatas:
            app_logger.info(
                f"[{timestamp_str}] /difficulties: 未加载到任何题库元数据，返回空列表。"
            )
        return metadatas
    except Exception as e:
        app_logger.error(
            f"[{timestamp_str}] /difficulties: 获取题库元数据时发生意外错误: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取题库难度列表时发生服务器内部错误。",
        ) from e


# endregion

# region 公开用户目录 API 端点
users_public_router = APIRouter(tags=["公共接口 (Public)"])


@users_public_router.get(
    "/users/directory",
    response_model=List[UserDirectoryEntry],
    summary="获取公开用户目录",  # 确保summary为中文
    description="公开接口，无需认证。返回系统中拥有特定公开角色标签（例如：管理员、出题人、运营经理、批阅员等）的用户子集，主要用于展示项目团队或关键贡献者等公开信息。",
    tags=["公共接口 (Public)"],
    responses={
        http_status.HTTP_200_OK: {
            "model": List[UserDirectoryEntry],
            "description": "成功获取用户目录列表",
        },  # 添加model到成功响应
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "获取用户目录时发生服务器内部错误"
        },
    },
)
async def get_users_directory():
    """
    提供一个公开的用户列表，这些用户拥有特殊角色（如管理员、出题员、运营管理员、批阅员）。
    此接口可用于例如显示网站的工作人员或关键人员列表。
    """
    app_logger.info("公开接口：请求具有特殊角色的用户目录。")
    try:
        all_users_from_db = await user_crud_instance.admin_get_all_users(
            limit=settings.num_questions_per_paper_default * 10
        )
    except Exception as e_users:  # Catch potential errors during user fetch
        app_logger.error(f"获取所有用户用于目录构建时出错: {e_users}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取用户数据时发生错误，无法生成目录。",
        ) from e_users

    # 定义哪些标签属于“特殊角色”
    special_role_tags = {
        UserTag.ADMIN,
        UserTag.EXAMINER,
        UserTag.MANAGER,
        UserTag.GRADER,
    }
    directory_entries: List[UserDirectoryEntry] = []

    for user_db_model in all_users_from_db:
        user_tags_set = set(user_db_model.tags)
        if not user_tags_set.isdisjoint(special_role_tags):
            directory_entries.append(
                UserDirectoryEntry.model_validate(user_db_model)
            )  # 使用 model_validate
    return directory_entries
    # No specific try-except for the list comprehension part as it's less likely to fail
    # if all_users_from_db is successfully fetched and UserDirectoryEntry.model_validate is robust.
    # However, if UserDirectoryEntry.model_validate could fail, more granular error handling might be needed.


app.include_router(users_public_router)  # 挂载用户目录路由
# endregion

# region Admin API 路由挂载
# 管理员相关API路由在 admin_routes.py 中定义，并在此处挂载到主应用
app.include_router(admin_router, prefix="/admin")  # 所有管理员接口统一前缀 /admin
app.include_router(ws_router)  # 挂载 WebSocket 路由
# endregion

# region 主执行块 (用于直接运行此文件进行开发)
if __name__ == "__main__":
    # 此部分仅在直接通过 `python app/main.py` (或类似方式) 运行此文件时执行。
    # 在生产部署时，通常由 Uvicorn、Gunicorn 等 ASGI 服务器直接加载 `app.main:app` 实例，
    # 而不会执行这里的 `uvicorn.run()`。

    log_file_to_log = (
        settings.log_file_name if settings else "exam_app.log (settings not loaded)"
    )

    app_logger.info(f"正在启动 FastAPI 考试应用程序 (版本: {app.version})...")
    app_logger.info(f"日志将写入到: {os.path.abspath(log_file_to_log)}")
    app_logger.info(f"应用域名 (APP_DOMAIN): {settings.app_domain}")
    app_logger.info(f"前端域名 (FRONTEND_DOMAIN) - CORS: {settings.frontend_domain}")
    app_logger.info(f"监听端口 (LISTENING_PORT): {settings.listening_port}")
    app_logger.info(f"数据存储类型 (DATA_STORAGE_TYPE): {settings.data_storage_type}")

    app_logger.info(
        f"试卷数据库文件 (如果使用JSON存储): '{settings.get_db_file_path('papers')}'"
    )
    app_logger.info(
        f"用户数据库文件 (如果使用JSON存储): '{settings.get_db_file_path('users')}'"
    )
    app_logger.info(f"题库索引文件: '{settings.get_library_index_path()}'")

    app_logger.info(
        "默认 Admin 用户 UID 为 'admin'。如果首次运行且数据库为空，请检查日志获取初始密码（如果自动生成）。"
    )
    app_logger.info(
        f"新试卷请求速率限制 (默认用户): {settings.rate_limits['default_user'].get_exam.limit} 次 / {settings.rate_limits['default_user'].get_exam.window} 秒。"
    )

    # 使用 uvicorn.run() 启动 ASGI 应用服务器
    uvicorn.run(
        "app.main:app",  # 指向 FastAPI 应用实例的字符串路径
        host="0.0.0.0",  # 监听所有可用网络接口
        port=settings.listening_port,  # 从配置读取监听端口
        log_level="info",  # Uvicorn 服务器自身的日志级别
        reload=True,  # 开发模式下启用代码修改后自动重载 (生产环境应禁用)
        # access_log=False # Uvicorn的访问日志已通过core.config中的日志配置进行管理
    )
# endregion
