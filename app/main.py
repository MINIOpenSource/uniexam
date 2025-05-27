# -*- coding: utf-8 -*-
# region 模块导入与初始设置
"""
FastAPI 应用主入口文件。

负责初始化FastAPI应用实例，加载配置，设置中间件，
挂载各个功能模块的API路由 (用户认证、核心答题、管理员接口等)，
并定义应用的生命周期事件 (启动和关闭时的任务)。
"""
import asyncio
import logging # 用于配置应用级日志
import os
from typing import List, Optional, Dict # 确保导入 Dict

import uvicorn
from uuid import UUID
from fastapi import FastAPI, Request, Depends, HTTPException, Query, status as http_status, APIRouter
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

# --- 核心模块导入 (使用相对路径) ---
from .core.config import settings, DifficultyLevel, setup_logging # 全局配置和枚举, setup_logging
from .core.security import ( # 安全和认证相关
    create_access_token,
    get_current_active_user_uid,
    RequireTags, # 权限检查依赖项
    UserTag # 用户标签枚举
)
from .core.rate_limiter import is_rate_limited # 速率限制检查函数

# --- CRUD 操作模块实例 ---
# 这些实例在 app.crud.__init__ 中创建并导出，方便统一管理
from .crud import (
    user_crud_instance, paper_crud_instance, qb_crud_instance, settings_crud_instance
)
from .utils.helpers import get_client_ip_from_request, format_short_uuid, get_current_timestamp_str # 导入工具函数

# --- Pydantic 模型导入 ---
from .models.user_models import UserCreate, UserProfileUpdate, UserPasswordUpdate, UserPublicProfile, UserDirectoryEntry
from .models.token_models import Token, AuthStatusResponse # 使用 Token, AuthStatusResponse
from .models.paper_models import PaperSubmissionPayload, ExamPaperResponse, GradingResultResponse, UpdateProgressResponse, HistoryItem, HistoryPaperDetailResponse
from .models.qb_models import LibraryIndexItem # 用于 /difficulties 接口

# --- 路由模块导入 ---
from .admin_routes import admin_router # 管理员接口路由

# endregion
#%%
# region 应用级日志记录器配置
# Logging is now configured by setup_logging in config.py, called when settings are loaded.
# We can still get a logger specific to this module.
app_logger = logging.getLogger(__name__)
# logging.basicConfig(level=settings.log_level) # 例如，如果settings中有log_level
# endregion

# region FastAPI 应用实例与全局变量初始化
app = FastAPI(
    title=settings.app_name,
    description="包含用户账户、Token认证、历史记录、题库管理及Cloudflare IP感知等功能的试卷API。",
    version="3.0.0", # 重大版本，因引入用户系统和大量API变更
    # openapi_url="/api/v1/openapi.json" # 自定义OpenAPI路径 (可选)
)

# CRUD 实例已从 app.crud.__init__ 导入

# 导入认证状态码
from .core.config import CODE_AUTH_SUCCESS, CODE_AUTH_WRONG, CODE_AUTH_DUPLICATE

# --- Cloudflare IP 范围 (全局变量，由后台任务更新) ---
# 这些变量由 app.core.config 初始化，并由后台任务更新
# from .core.config import cloudflare_ipv4_ranges, cloudflare_ipv6_ranges # 可以这样访问
# 或者通过 settings 对象访问 (如果 settings 包含这些动态加载的范围)
# 当前 Cloudflare IP 获取逻辑在 helpers.py 的 get_client_ip_from_request 中直接使用全局变量
# 更好的做法是将这些动态数据封装在一个服务或管理器中

# endregion

# region FastAPI 生命周期事件 (Startup & Shutdown)

async def main_periodic_tasks():
    """运行所有主要的定期后台任务。"""
    # Cloudflare IP 更新任务
    async def periodic_cloudflare_ip_update():
        from .utils.helpers import fetch_and_update_cloudflare_ips_once # 延迟导入
        while True:
            await fetch_and_update_cloudflare_ips_once() # 启动时获取一次
            await asyncio.sleep(settings.cloudflare_ips.fetch_interval_seconds)
            
    # 数据库持久化和Token清理任务
    async def periodic_db_and_token_tasks():
        while True:
            await asyncio.sleep(settings.db_persist_interval_seconds)
            app_logger.info(f"后台任务：尝试定期 ({settings.db_persist_interval_seconds}s) 执行数据库相关任务...")
            if hasattr(paper_crud_instance, '_persist_papers_to_file_async'): # 确保方法存在
                await paper_crud_instance._persist_papers_to_file_async()
            if hasattr(user_crud_instance, '_persist_users_to_file_async'): # 确保方法存在
                 await user_crud_instance._persist_users_to_file_async() # 用户数据也可能需要定期保存（如果非关键操作不立即写盘）
            if hasattr(user_crud_instance, 'cleanup_expired_tokens'): # 确保方法存在
                await user_crud_instance.cleanup_expired_tokens()


    # 启动时首先获取一次Cloudflare IP
    # from .utils.helpers import fetch_and_update_cloudflare_ips_once # 移到 periodic_cloudflare_ip_update 内部
    # await fetch_and_update_cloudflare_ips_once()

    # 创建并运行后台任务
    # asyncio.create_task(periodic_cloudflare_ip_update()) # Cloudflare IP 更新
    # asyncio.create_task(periodic_db_and_token_tasks()) # 数据库持久化和Token清理
    # FastAPI 的 @app.on_event("startup") 中创建的任务会在事件循环中运行

@app.on_event("startup")
async def startup_event():
    """应用启动时执行的事件。"""
    app_logger.info("应用启动事件：初始化并开始定期后台任务。")
    
    # 启动后台任务
    # 确保这些任务不会阻塞启动过程
    asyncio.create_task(main_periodic_tasks())


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行的事件。"""
    app_logger.info("应用关闭事件：执行最后一次数据保存...")
    if hasattr(paper_crud_instance, '_persist_papers_to_file_async'):
        await paper_crud_instance._persist_papers_to_file_async()
    if hasattr(user_crud_instance, '_persist_users_to_file_async'):
        await user_crud_instance._persist_users_to_file_async()
    app_logger.info("数据已保存，应用即将关闭。")
# endregion

# region FastAPI 中间件 (例如 CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_domain, "http://localhost", "http://127.0.0.1"], # 从配置读取前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# endregion

# region 用户认证 API 端点 (使用 auth_router)
auth_router = APIRouter(tags=["User Authentication"]) # 用户认证相关接口

@auth_router.post(
    "/signin",
    response_model=Token,
    status_code=http_status.HTTP_201_CREATED,
    responses={
        http_status.HTTP_409_CONFLICT: {"model": AuthStatusResponse, "description": "User already exists"},
        http_status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Too many requests"}
    }
)
async def sign_up_new_user(payload: UserCreate, request: Request):
    """用户注册接口，成功则返回包含Token的响应。"""
    client_ip = get_client_ip_from_request(request) # helpers.py 中的函数会使用其内部的全局CF IP列表
    if is_rate_limited(client_ip, "auth_attempts"): # 使用 rate_limiter 中的函数
        raise HTTPException(status_code=http_status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many sign-up attempts.")
    
    user = await user_crud_instance.create_user(payload)
    if not user:
        app_logger.warning(f"用户注册失败：用户名 '{payload.uid}' 已存在 (IP: {client_ip})。")
        return JSONResponse(
            status_code=http_status.HTTP_409_CONFLICT,
            content={"status_code": CODE_AUTH_DUPLICATE, "message": "Username already exists."}
        )
    
    token_str = await create_access_token(user.uid, user.tags)
    app_logger.info(f"新用户 '{payload.uid}' 注册成功并登录 (IP: {client_ip})。")
    return Token(access_token=token_str)

@auth_router.post(
    "/login",
    response_model=Token,
    responses={
        http_status.HTTP_401_UNAUTHORIZED: {"model": AuthStatusResponse, "description": "Incorrect username or password"},
        http_status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Too many requests"}
    }
)
async def login_for_access_token(payload: UserCreate, request: Request):
    """用户登录接口，成功则返回Token。"""
    client_ip = get_client_ip_from_request(request)
    if is_rate_limited(client_ip, "auth_attempts"):
        raise HTTPException(status_code=http_status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts.")
    from .core.security import verify_password, validate_token_and_get_user_info, invalidate_token # 延迟导入
    user = user_crud_instance.get_user_by_uid(payload.uid)
    if not user or not verify_password(payload.password, user.hashed_password):
        app_logger.warning(f"用户 '{payload.uid}' 登录失败：用户名或密码错误 (IP: {client_ip})。")
        return JSONResponse(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            content={"status_code": CODE_AUTH_WRONG, "message": "Incorrect username or password."}
        )
    
    token_str = await create_access_token(user.uid, user.tags)
    app_logger.info(f"用户 '{payload.uid}' 登录成功 (IP: {client_ip})。")
    return Token(access_token=token_str)

@auth_router.get(
    "/login", # GET /login?token={old_token} 用于刷新
    response_model=Token,
    summary="刷新访问Token",
    responses={401: {"model": AuthStatusResponse, "description": "Invalid or expired token"}}
)
async def refresh_access_token(
    token_to_refresh: str = Query(..., alias="token", description="需要刷新的旧Token")
):
    """使用有效的旧Token获取一个新的访问Token，旧Token将同时失效。"""
    from .core.security import validate_token_and_get_user_info, invalidate_token # 延迟导入
    
    user_info = await validate_token_and_get_user_info(token_to_refresh)
    if not user_info:
        app_logger.warning(f"刷新Token失败：旧Token无效或已过期 (部分Token: {token_to_refresh[:8]}...)")
        return JSONResponse(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            content={"status_code": CODE_AUTH_WRONG, "message": "Invalid or expired token provided for refresh."}
        )
    
    await invalidate_token(token_to_refresh) # 使旧Token失效
    new_token_str = await create_access_token(user_info["user_uid"], user_info["tags"])
    
    app_logger.info(f"用户 '{user_info['user_uid']}' 的Token (部分旧Token: {token_to_refresh[:8]}...) 已成功刷新。")
    return Token(access_token=new_token_str)

app.include_router(auth_router)
# endregion

# region 用户个人信息管理 API 端点
user_profile_router = APIRouter(
    prefix="/users/me", # 用户管理自己的信息
    tags=["User Profile"],
    dependencies=[Depends(get_current_active_user_uid)] # 所有接口都需要有效Token
)

@user_profile_router.get("", response_model=UserPublicProfile, summary="获取当前用户信息")
async def read_users_me(current_user_uid: str = Depends(get_current_active_user_uid)):
    """获取当前认证用户的公开个人资料。"""
    from .core.security import get_password_hash, verify_password # 延迟导入
    user = user_crud_instance.get_user_by_uid(current_user_uid)
    if not user:
        # 这种情况理论上不应发生，因为Token验证时用户应该存在
        app_logger.error(f"获取当前用户信息失败：用户 '{current_user_uid}' 在数据库中未找到，但Token有效。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="User not found.")
    return UserPublicProfile.model_validate(user) # 从UserInDB转换为UserPublicProfile

@user_profile_router.put("", response_model=UserPublicProfile, summary="更新当前用户个人资料")
async def update_users_me(
    profile_data: UserProfileUpdate,
    current_user_uid: str = Depends(get_current_active_user_uid)
):
    """更新当前认证用户的昵称、邮箱或QQ号。"""
    updated_user = await user_crud_instance.update_user_profile(current_user_uid, profile_data)
    if not updated_user:
        app_logger.warning(f"用户 '{current_user_uid}' 更新个人资料失败（可能用户不存在或数据无效）。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="User not found or update data invalid.")
    return UserPublicProfile.model_validate(updated_user)

@user_profile_router.put("/password", status_code=http_status.HTTP_204_NO_CONTENT, summary="修改当前用户密码")
async def update_users_me_password(
    password_data: UserPasswordUpdate,
    current_user_uid: str = Depends(get_current_active_user_uid)
):
    from .core.security import get_password_hash, verify_password # 延迟导入
    """当前认证用户修改自己的密码。"""
    user_in_db = user_crud_instance.get_user_by_uid(current_user_uid)
    if not user_in_db:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="User not found.") # 理论上不会发生
    
    if not verify_password(password_data.current_password, user_in_db.hashed_password):
        app_logger.warning(f"用户 '{current_user_uid}' 修改密码失败：当前密码不正确。")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Incorrect current password.")
    
    new_hashed_password = get_password_hash(password_data.new_password)
    success = await user_crud_instance.update_user_password(current_user_uid, new_hashed_password)
    if not success:
        # 理论上如果用户存在，这里应该总是成功
        app_logger.error(f"用户 '{current_user_uid}' 修改密码时发生未知错误。")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update password.")
    
    app_logger.info(f"用户 '{current_user_uid}' 成功修改密码。")
    # 成功修改密码后，可以考虑让用户所有旧Token失效，但这需要更复杂的Token管理
    return # 返回 204 No Content

app.include_router(user_profile_router)
# endregion

# region 核心答题 API 端点 (使用 exam_router)
exam_router = APIRouter(
    dependencies=[Depends(get_current_active_user_uid)], # 所有接口都需要有效Token
    tags=["Exam Taking"]
)

@exam_router.get("/get_exam", response_model=ExamPaperResponse, summary="请求一份新试卷")
async def request_new_exam_paper(
    request: Request,
    current_user_uid: str = Depends(get_current_active_user_uid),
    difficulty: DifficultyLevel = Query(default=DifficultyLevel.hybrid, description="新试卷的难度级别"),
    num_questions: Optional[int] = Query(
        None, 
        ge=1, 
        le=200, # 假设最大题目数限制
        description="请求的题目数量 (可选, 覆盖该难度默认题量)"
    )
):
    from .core.security import validate_token_and_get_user_info # 延迟导入
    """为认证用户创建一份指定难度和（可选）指定题目数量的新试卷。"""
    client_ip = get_client_ip_from_request(request)
    timestamp_str = get_current_timestamp_str()
    
    # 检查用户标签，admin不受速率限制
    user_info = await validate_token_and_get_user_info(request.query_params.get("token","")) # 重新获取user_info以检查标签
    user_tags = user_info.get("tags", []) if user_info else []

    if UserTag.ADMIN not in user_tags:
        if is_rate_limited(client_ip, "get_exam", user_tags): # 传入用户标签
            app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}, 标签: {[t.value for t in user_tags]}) 请求新试卷，但超出速率限制。")
            raise HTTPException(status_code=http_status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests for new exam.")
    
    app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 请求一份新的 [{difficulty.value}] 试卷 (题量: {num_questions or '默认'})。")
    try:
        new_paper_client_data = await paper_crud_instance.create_new_paper(
            request=request, 
            user_uid=current_user_uid, 
            difficulty=difficulty, 
            num_questions_override=num_questions
        )
        short_id = format_short_uuid(new_paper_client_data["paper_id"])
        app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 成功创建新试卷 [{difficulty.value}]：{short_id}")
        return ExamPaperResponse(
            paper_id=new_paper_client_data["paper_id"],
            difficulty=new_paper_client_data["difficulty"],
            paper=new_paper_client_data["paper"]
            # submitted_answers_for_resume (finished) 已从 ExamPaperResponse 移除
        )
    except ValueError as ve: # 例如题库题目不足
        app_logger.warning(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 创建新试卷失败 (ValueError): {ve}")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        app_logger.error(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 创建新试卷时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating new exam: {str(e)}")

@exam_router.post("/update", response_model=UpdateProgressResponse, summary="更新未完成试卷的答题进度")
def update_exam_progress(payload: PaperSubmissionPayload, request: Request, current_user_uid: str = Depends(get_current_active_user_uid)): # ... (逻辑不变)
    client_ip = get_client_ip_from_request(request); timestamp_str = get_current_timestamp_str(); short_paper_id = format_short_uuid(payload.paper_id)
    app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 正在更新试卷 {short_paper_id} 的进度。")
    try:
        update_result = paper_crud_instance.update_paper_progress(payload.paper_id, current_user_uid, payload.result, request)
        status_code_text = update_result.get("status_code", "UNKNOWN_ERROR")
        if status_code_text == "PROGRESS_SAVED": app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 成功保存试卷 {short_paper_id} 进度。"); return UpdateProgressResponse(**update_result)
        elif status_code_text == "NOT_FOUND": app_logger.warning(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度失败：未找到或权限不足。"); raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=update_result.get("message", "Paper not found or access denied."))
        elif status_code_text == "ALREADY_COMPLETED": app_logger.warning(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度失败：试卷已完成。"); raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail=update_result.get("message", "This paper has already been completed."))
        elif status_code_text == "INVALID_ANSWERS_LENGTH": app_logger.warning(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度失败：答案数量错误。"); raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=update_result.get("message", "Invalid number of answers."))
        else: app_logger.error(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度时发生已知错误: {update_result}"); raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=update_result.get("message", "Failed to update progress."))
    except HTTPException as http_exc: raise http_exc
    except Exception as e: app_logger.error(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 更新试卷 {short_paper_id} 进度时发生意外错误: {e}", exc_info=True); raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error updating progress: {str(e)}")

@exam_router.post("/finish", response_model=GradingResultResponse, summary="提交试卷答案进行批改")
def submit_exam_paper(payload: PaperSubmissionPayload, request: Request, current_user_uid: str = Depends(get_current_active_user_uid)): # ... (逻辑不变)
    client_ip = get_client_ip_from_request(request); timestamp_str = get_current_timestamp_str(); short_paper_id = format_short_uuid(payload.paper_id)
    app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 正在提交试卷 {short_paper_id} 进行批改。")
    try:
        outcome = paper_crud_instance.grade_paper_submission(payload.paper_id, current_user_uid, payload.result, request)
        response_data = GradingResultResponse(**outcome); score, status_text = response_data.score, outcome.get("status_code")
        log_msg_prefix = f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 提交试卷 {short_paper_id} 的答案"
        if status_text == "PASSED": app_logger.info(f"{log_msg_prefix}，获得 {score if score is not None else 'N/A'} 分 ({response_data.score_percentage}%)，通过考试，入群码：{response_data.passcode or 'N/A'}")
        elif status_text == "FAILED": app_logger.info(f"{log_msg_prefix}，获得 {score if score is not None else 'N/A'} 分 ({response_data.score_percentage}%)，未能通过考试")
        elif status_text == "ALREADY_GRADED": app_logger.info(f"{log_msg_prefix}，但该试卷已经有作答记录")
        elif status_text == "NOT_FOUND": app_logger.info(f"{log_msg_prefix}，但试卷不存在或权限不足")
        elif status_text == "INVALID_SUBMISSION": app_logger.info(f"{log_msg_prefix}，但提交数据无效")
        elif status_text == "INVALID_PAPER_STRUCTURE": app_logger.warning(f"{log_msg_prefix}，但试卷内部结构错误，无法批改")
        else: app_logger.warning(f"{log_msg_prefix}，结果: {status_text}, 详情: {outcome}")
        return JSONResponse(content=response_data.model_dump(exclude_none=True), status_code=200)
    except HTTPException as http_exc: raise http_exc
    except Exception as e: app_logger.error(f"[{timestamp_str}] 用户 '{current_user_uid}' (IP {client_ip}) 提交试卷 {short_paper_id} 时发生意外服务器错误: {e}", exc_info=True); error_detail = {"code": 500, "status_code": "SERVER_ERROR", "message": f"Error processing submission: {str(e)}"}; return JSONResponse(content=error_detail, status_code=500)

@exam_router.get("/history", response_model=List[HistoryItem], summary="获取当前用户的答题历史记录")
def get_user_exam_history(current_user_uid: str = Depends(get_current_active_user_uid)): # ... (逻辑不变)
    timestamp_str = get_current_timestamp_str(); app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' 请求答题历史记录。")
    history_data = paper_crud_instance.get_user_history(current_user_uid); return [HistoryItem(**item) for item in history_data]

@exam_router.get("/history_paper", response_model=HistoryPaperDetailResponse, summary="获取指定历史试卷的详细信息")
def get_user_history_paper_detail(paper_id: UUID = Query(..., description="要获取详情的历史试卷ID"), current_user_uid: str = Depends(get_current_active_user_uid)): # ... (逻辑不变)
    timestamp_str = get_current_timestamp_str(); short_paper_id = format_short_uuid(paper_id)
    app_logger.info(f"[{timestamp_str}] 用户 '{current_user_uid}' 请求历史试卷 {short_paper_id} 的详情。")
    paper_detail = paper_crud_instance.get_user_paper_detail_for_history(str(paper_id), current_user_uid)
    if not paper_detail: app_logger.warning(f"[{timestamp_str}] 用户 '{current_user_uid}' 请求的历史试卷 {short_paper_id} 未找到或无权限查看。"); raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Specified history paper not found or access denied.")
    return HistoryPaperDetailResponse(**paper_detail)

app.include_router(exam_router)
# endregion

# region 题库元数据接口 (公开，无需Token)
@app.get(
    "/difficulties",
    response_model=List[LibraryIndexItem],
    summary="获取所有可用题库的元数据列表",
    tags=["Question Bank"]
)
async def get_available_difficulties():
    """
    获取系统中所有已定义的题库难度及其元数据信息。
    这些信息从 `data/library/index.json` 文件读取。
    """
    timestamp_str = get_current_timestamp_str()
    app_logger.info(f"[{timestamp_str}] 公开接口：请求可用题库难度列表。")
    try:
        metadatas = await qb_crud_instance.get_all_library_metadatas()
        if not metadatas:
            app_logger.warning(f"[{timestamp_str}] /difficulties: 未能加载任何题库元数据。")
            # 即使为空也返回200和空列表，表示系统配置中没有题库
        return metadatas
    except Exception as e:
        app_logger.error(f"[{timestamp_str}] /difficulties: 获取题库元数据时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error fetching difficulty metadata.")
# endregion

# region Public Users Directory API Endpoint
users_public_router = APIRouter(tags=["Users Directory"])

@users_public_router.get(
    "/users/directory",
    response_model=List[UserDirectoryEntry],
    summary="Get a list of users with special roles/categories"
)
async def get_users_directory():
    """
    Provides a public list of users who have special roles (e.g., admin, examiner, manager, grader).
    This can be used, for example, to display a list of staff or key personnel.
    """
    all_users_from_db = user_crud_instance.admin_get_all_users(limit=settings.num_questions_per_paper_default * 10) # Fetch a large number, or implement better pagination if needed
    
    special_role_tags = {UserTag.ADMIN, UserTag.EXAMINER, UserTag.MANAGER, UserTag.GRADER}
    directory_entries: List[UserDirectoryEntry] = []

    for user_db_model in all_users_from_db:
        user_tags_set = set(user_db_model.tags)
        # Check if the user has any of the special role tags
        if not user_tags_set.isdisjoint(special_role_tags):
            directory_entries.append(
                UserDirectoryEntry(uid=user_db_model.uid, nickname=user_db_model.nickname, tags=user_db_model.tags)
            )
    return directory_entries

app.include_router(users_public_router)
# endregion

# region Admin API 路由挂载
# admin_routes.py 中定义了 admin_router
app.include_router(admin_router)
# endregion

# region 主执行块
if __name__ == "__main__":
    # 此部分仅在直接运行此文件时执行 (例如 python app/main.py)
    # 生产部署时，通常由 Uvicorn 或 Gunicorn 等 ASGI 服务器直接加载 `app.main:app`
    
    # 从 settings 对象获取日志文件名，确保日志配置在应用启动信息之前
    log_file_to_log = settings.log_file_name if settings else "exam_app.log (settings not loaded)"
    
    app_logger.info(f"正在启动 FastAPI 考试应用程序 (版本: {app.version})...")
    app_logger.info(f"日志将写入到: {os.path.abspath(log_file_to_log)}")
    app_logger.info(f"应用域名 (APP_DOMAIN): {settings.app_domain}")
    app_logger.info(f"前端域名 (FRONTEND_DOMAIN) - CORS: {settings.frontend_domain}")
    app_logger.info(f"监听端口 (LISTENING_PORT): {settings.listening_port}")

    app_logger.info(f"试卷数据库将每隔 {settings.db_persist_interval_seconds} 秒持久化到: '{settings.get_db_file_path('papers')}'")
    app_logger.info(f"用户数据库将持久化到: '{settings.get_db_file_path('users')}'")
    app_logger.info(f"题库索引文件: '{settings.get_library_index_path()}'")
    
    app_logger.info("默认 Admin 用户 UID 为 'admin'。如果首次运行，请检查日志获取初始密码（如果生成）。")
    app_logger.info(f"新试卷请求速率限制 (默认用户): {settings.rate_limits['default_user'].get_exam.limit} 次 / {settings.rate_limits['default_user'].get_exam.window} 秒。")
    
    uvicorn.run(
        "app.main:app", # 指向 FastAPI 应用实例
        host="0.0.0.0", # 监听所有可用网络接口
        port=settings.listening_port,
        log_level="info", # Uvicorn自身的日志级别
        reload=True # 开发模式下启用自动重载 (生产环境应禁用)
        # access_log=False # Uvicorn的访问日志已通过config.py中的配置禁用 (如果需要)
    )
# endregion
