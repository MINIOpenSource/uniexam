# -*- coding: utf-8 -*-
"""
管理员后台 API 路由模块。

此模块定义了所有与管理员操作相关的API端点，例如：
- 应用配置管理 (获取、更新)
- 用户管理 (列表、详情、更新)
- 试卷管理 (列表、详情、删除)
- 题库管理 (查看题库、添加题目、删除题目)
- 阅卷接口 (获取待批阅列表、获取题目详情、提交批阅结果)

所有此模块下的路由都需要管理员权限（通过 `require_admin` 依赖项进行验证）。
"""
# region 模块导入区域开始
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    status as http_status,
)

from app.utils.export_utils import data_to_csv, data_to_xlsx

from ..services.audit_logger import audit_logger_service
from ..utils.helpers import get_client_ip_from_request
from .core.config import DifficultyLevel, settings
from .core.security import (
    RequireTags,
    get_all_active_token_info,
    invalidate_all_tokens_for_user,
    invalidate_token,
    require_admin,
)
from .crud import (
    paper_crud_instance as paper_crud,
    qb_crud_instance as qb_crud,
    settings_crud_instance as settings_crud,
    user_crud_instance as user_crud,
)
from .models.config_models import (
    SettingsResponseModel,
    SettingsUpdatePayload,
)
from .models.enums import QuestionTypeEnum
from .models.paper_models import (
    GradeSubmissionPayload,
    PaperAdminView,
    PaperFullDetailModel,
    PendingGradingPaperItem,
    SubjectiveQuestionForGrading,
)
from .models.qb_models import (
    LibraryIndexItem,
    QuestionBank,
    QuestionModel,
)
from .models.user_models import (
    AdminUserUpdate,
    UserPublicProfile,
    UserTag,
)

# endregion 模块导入区域结束

# region 全局变量与初始化区域开始
_admin_routes_logger = logging.getLogger(__name__)

admin_router = APIRouter(
    tags=["管理员接口 (Admin)"],
    dependencies=[Depends(require_admin)],
    responses={
        http_status.HTTP_401_UNAUTHORIZED: {"description": "Token缺失或无效 (Unauthorized)"},
        http_status.HTTP_403_FORBIDDEN: {"description": "权限不足 (非管理员用户) (Forbidden)"},
    },
)
# endregion 全局变量与初始化区域结束


# region 管理员设置API端点 (Admin Settings API)
@admin_router.get(
    "/settings",
    response_model=SettingsResponseModel,
    summary="获取当前系统配置",
    description="管理员获取当前应用的主要配置项信息...",
)
async def admin_get_settings(request: Request):
    actor_uid = getattr(request.state, "current_user_uid", "unknown_admin")
    client_ip = get_client_ip_from_request(request)
    _admin_routes_logger.info(f"管理员 '{actor_uid}' (IP: {client_ip}) 请求获取应用配置。")

    current_settings_from_file = settings_crud.get_current_settings_from_file()
    try:
        return SettingsResponseModel(**current_settings_from_file)
    except Exception as e:
        _admin_routes_logger.error(f"将文件配置转换为SettingsResponseModel时出错: {e}")
        return SettingsResponseModel()

@admin_router.post(
    "/settings",
    response_model=SettingsResponseModel,
    summary="更新系统配置 (仅限高级管理员)",
    description="高级管理员 (具有 MANAGER 标签) 更新应用的部分或全部可配置项...",
    dependencies=[Depends(RequireTags({UserTag.MANAGER}))]
)
async def admin_update_settings(request: Request, payload: SettingsUpdatePayload): # [中文]: payload 是请求体, request 是依赖项
    actor_info = getattr(request.state, "user_info_from_token", {"user_uid": "unknown_manager", "tags": [UserTag.MANAGER]})
    actor_uid = actor_info.get("user_uid", "unknown_manager")
    client_ip = get_client_ip_from_request(request)
    updated_keys = list(payload.model_dump(exclude_unset=True).keys())
    _admin_routes_logger.info(f"管理员 '{actor_uid}' (IP: {client_ip}) 尝试更新应用配置，数据: {payload.model_dump_json(indent=2)}")

    try:
        await settings_crud.update_settings_file_and_reload(payload.model_dump(exclude_unset=True))
        settings_from_file_after_update = settings_crud.get_current_settings_from_file()
        _admin_routes_logger.info(f"管理员 '{actor_uid}' 成功更新并重新加载了应用配置。")
        await audit_logger_service.log_event(
            action_type="ADMIN_UPDATE_CONFIG", status="SUCCESS",
            actor_uid=actor_uid, actor_ip=client_ip,
            details={"message": "应用配置已成功更新", "updated_keys": updated_keys}
        )
        return SettingsResponseModel(**settings_from_file_after_update)
    except ValueError as e_val:
        _admin_routes_logger.warning(f"管理员 '{actor_uid}' 更新配置失败 (数据验证错误): {e_val}")
        await audit_logger_service.log_event(
            action_type="ADMIN_UPDATE_CONFIG", status="FAILURE",
            actor_uid=actor_uid, actor_ip=client_ip,
            details={"error": str(e_val), "attempted_keys": updated_keys}
        )
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e_val)) from e_val
    except IOError as e_io:
        _admin_routes_logger.error(f"管理员 '{actor_uid}' 更新配置失败 (文件写入错误): {e_io}")
        await audit_logger_service.log_event(
            action_type="ADMIN_UPDATE_CONFIG", status="FAILURE",
            actor_uid=actor_uid, actor_ip=client_ip,
            details={"error": f"文件写入错误: {e_io}", "attempted_keys": updated_keys}
        )
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="配置文件写入失败。") from e_io
    except RuntimeError as e_rt:
        _admin_routes_logger.error(f"管理员 '{actor_uid}' 更新配置失败 (运行时错误): {e_rt}")
        await audit_logger_service.log_event(
            action_type="ADMIN_UPDATE_CONFIG", status="FAILURE",
            actor_uid=actor_uid, actor_ip=client_ip,
            details={"error": f"运行时错误: {e_rt}", "attempted_keys": updated_keys}
        )
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e_rt)) from e_rt
    except Exception as e:
        _admin_routes_logger.error(f"管理员 '{actor_uid}' 更新配置时发生未知错误: {e}", exc_info=True)
        await audit_logger_service.log_event(
            action_type="ADMIN_UPDATE_CONFIG", status="FAILURE",
            actor_uid=actor_uid, actor_ip=client_ip,
            details={"error": f"未知错误: {e}", "attempted_keys": updated_keys}
        )
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新配置时发生意外错误。") from e
# endregion 管理员设置API端点结束

# region 管理员用户管理API端点 (Admin User Management API)
@admin_router.get(
    "/users",
    summary="管理员获取用户列表 (支持CSV/XLSX导出)",
    description="获取用户列表。可通过 'format' 查询参数导出为 CSV 或 XLSX 文件。"
)
async def admin_get_all_users(
    request: Request,
    skip: int = Query(0, ge=0, description="跳过的用户数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的用户数上限 (导出时此限制可能被忽略或调整)"),
    export_format: Optional[str] = Query(None, description="导出格式 (csv 或 xlsx)", alias="format", regex="^(csv|xlsx)$")
):
    actor_uid = getattr(request.state, "current_user_uid", "unknown_admin")
    client_ip = get_client_ip_from_request(request)
    _admin_routes_logger.info(f"管理员 '{actor_uid}' (IP: {client_ip}) 请求用户列表，skip={skip}, limit={limit}, format={export_format}。")

    effective_limit = limit
    if export_format:
        _admin_routes_logger.info(f"导出请求: 正在尝试获取所有用户进行导出 (原 limit={limit} 可能被覆盖)。")
        effective_limit = 1_000_000

    users_in_db = await user_crud.admin_get_all_users(skip=0 if export_format else skip, limit=effective_limit)

    if export_format:
        if not users_in_db:
            _admin_routes_logger.info("没有用户数据可导出。")

        data_to_export: List[Dict[str, Any]] = []
        for user in users_in_db:
            tags_str = ", ".join([tag.value for tag in user.tags]) if user.tags else ""
            data_to_export.append({
                "用户ID": user.uid,
                "昵称": user.nickname,
                "邮箱": user.email,
                "QQ": user.qq,
                "标签": tags_str,
            })

        headers = ["用户ID", "昵称", "邮箱", "QQ", "标签"]
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"用户列表_{current_time}.{export_format}"

        if export_format == "csv":
            _admin_routes_logger.info(f"准备导出用户列表到 CSV 文件: {filename}")
            return data_to_csv(data_list=data_to_export, headers=headers, filename=filename)
        elif export_format == "xlsx":
            _admin_routes_logger.info(f"准备导出用户列表到 XLSX 文件: {filename}")
            return data_to_xlsx(data_list=data_to_export, headers=headers, filename=filename)

    if not users_in_db and skip > 0 :
        _admin_routes_logger.info(f"用户列表查询结果为空 (skip={skip}, limit={limit})。")

    return [UserPublicProfile.model_validate(user) for user in users_in_db]

@admin_router.get("/users/{user_uid}", response_model=UserPublicProfile, summary="管理员获取特定用户信息")
async def admin_get_user(user_uid: str = Path(..., description="要获取详情的用户的UID"), request: Request = Depends(lambda r: r) ):
    actor_uid = getattr(request.state, "current_user_uid", "unknown_admin")
    client_ip = get_client_ip_from_request(request)
    _admin_routes_logger.info(f"管理员 '{actor_uid}' (IP: {client_ip}) 请求用户 '{user_uid}' 的详细信息。")
    user = await user_crud.get_user_by_uid(user_uid)
    if not user:
        _admin_routes_logger.warning(f"管理员 '{actor_uid}' 请求用户 '{user_uid}' 失败：用户未找到。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="用户未找到")
    return UserPublicProfile.model_validate(user)

@admin_router.put("/users/{user_uid}", response_model=UserPublicProfile, summary="管理员更新特定用户信息")
async def admin_update_user_info(
    update_payload: AdminUserUpdate, # Body parameter first
    user_uid: str = Path(..., description="要更新信息的用户的UID"),
    request: Request = Depends(lambda r: r)
):
    current_admin_info = getattr(request.state, "user_info_from_token", {"user_uid": "unknown_admin", "tags": []})
    actor_uid = current_admin_info.get("user_uid", "unknown_admin")
    current_admin_tags = set(current_admin_info.get("tags", []))
    client_ip = get_client_ip_from_request(request)

    _admin_routes_logger.info(f"管理员 '{actor_uid}' (IP: {client_ip}) 尝试更新用户 '{user_uid}' 的信息，数据: {update_payload.model_dump_json(exclude_none=True)}")

    target_user = await user_crud.get_user_by_uid(user_uid)
    if not target_user:
        _admin_routes_logger.warning(f"管理员 '{actor_uid}' 更新用户 '{user_uid}' 失败：目标用户未找到。")
        await audit_logger_service.log_event(
            action_type="ADMIN_UPDATE_USER", status="FAILURE",
            actor_uid=actor_uid, actor_ip=client_ip,
            target_resource_type="USER", target_resource_id=user_uid,
            details={"message": "目标用户未找到"}
        )
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="目标用户未找到。")

    target_user_tags = set(target_user.tags)

    if UserTag.MANAGER in target_user_tags:
        if UserTag.MANAGER not in current_admin_tags:
            _admin_routes_logger.warning(f"权限拒绝：管理员 '{actor_uid}' 尝试修改高级管理员 '{user_uid}' 的信息。")
            await audit_logger_service.log_event(
                action_type="ADMIN_UPDATE_USER", status="FAILURE",
                actor_uid=actor_uid, actor_ip=client_ip,
                target_resource_type="USER", target_resource_id=user_uid,
                details={"message": "权限不足：普通管理员不能修改高级管理员的信息。"}
            )
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="普通管理员不能修改高级管理员的信息。")

    is_modifying_sensitive_fields = update_payload.tags is not None
    if UserTag.ADMIN in target_user_tags and UserTag.MANAGER not in target_user_tags:
        if is_modifying_sensitive_fields and UserTag.MANAGER not in current_admin_tags:
            _admin_routes_logger.warning(f"权限拒绝：管理员 '{actor_uid}' 尝试修改管理员 '{user_uid}' 的敏感信息 (标签)。")
            await audit_logger_service.log_event(
                action_type="ADMIN_UPDATE_USER", status="FAILURE",
                actor_uid=actor_uid, actor_ip=client_ip,
                target_resource_type="USER", target_resource_id=user_uid,
                details={"message": "权限不足：普通管理员不能修改其他管理员的标签。"}
            )
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="普通管理员不能修改其他管理员的标签。只有高级管理员可以。")

    updated_user = await user_crud.admin_update_user(user_uid, update_payload)

    if not updated_user:
        _admin_routes_logger.warning(f"管理员 '{actor_uid}' 更新用户 '{user_uid}' 失败：CRUD操作返回None (可能是内部错误)。")
        await audit_logger_service.log_event(
            action_type="ADMIN_UPDATE_USER", status="FAILURE",
            actor_uid=actor_uid, actor_ip=client_ip,
            target_resource_type="USER", target_resource_id=user_uid,
            details={"message": "用户更新操作在数据库层面失败。"}
        )
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="用户更新操作失败。")

    _admin_routes_logger.info(f"管理员 '{actor_uid}' 成功更新用户 '{user_uid}' 的信息。")
    await audit_logger_service.log_event(
        action_type="ADMIN_UPDATE_USER", status="SUCCESS",
        actor_uid=actor_uid, actor_ip=client_ip,
        target_resource_type="USER", target_resource_id=user_uid,
        details={"updated_fields": list(update_payload.model_dump(exclude_unset=True).keys())}
    )
    return UserPublicProfile.model_validate(updated_user)
# endregion 管理员用户管理API端点结束

# region 管理员试卷管理API端点 (Admin Paper Management API)
@admin_router.get(
    "/papers",
    summary="管理员获取所有试卷摘要列表 (支持CSV/XLSX导出)",
    description="获取所有试卷的摘要列表。支持分页、筛选和导出功能。"
)
async def admin_get_all_papers_summary(
    request: Request,
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数 (导出时可能被覆盖)"),
    user_uid_filter: Optional[str] = Query(None, alias="user_uid", description="按用户ID筛选"),
    difficulty_filter: Optional[DifficultyLevel] = Query(None, alias="difficulty", description="按难度筛选"),
    status_filter: Optional[str] = Query(None, alias="status", description="按状态筛选 (例如: 'completed', 'in_progress')"),
    export_format: Optional[str] = Query(None, description="导出格式 (csv 或 xlsx)", alias="format", regex="^(csv|xlsx)$")
):
    _admin_routes_logger.info(
        f"管理员请求试卷摘要列表，skip={skip}, limit={limit}, user_uid={user_uid_filter}, "
        f"difficulty={difficulty_filter.value if difficulty_filter else None}, status={status_filter}, format={export_format}。"
    )

    effective_limit = limit
    fetch_skip = skip
    if export_format:
        _admin_routes_logger.info("试卷列表导出请求: 正在尝试获取所有匹配筛选条件的试卷进行导出。")
        effective_limit = 1_000_000
        fetch_skip = 0

    try:
        all_papers_data = await paper_crud.admin_get_all_papers_summary(
            skip=fetch_skip,
            limit=effective_limit,
            user_uid=user_uid_filter,
            difficulty=difficulty_filter.value if difficulty_filter else None,
            status=status_filter
        )

        if export_format:
            if not all_papers_data:
                _admin_routes_logger.info("没有试卷数据可导出 (基于当前筛选条件)。")

            data_to_export: List[Dict[str, Any]] = []
            for paper_dict in all_papers_data:
                pass_status_str = ""
                if paper_dict.get('pass_status') is True:
                    pass_status_str = "通过"
                elif paper_dict.get('pass_status') is False:
                    pass_status_str = "未通过"

                difficulty_val = paper_dict.get('difficulty', '')
                if isinstance(difficulty_val, DifficultyLevel):
                    difficulty_str = difficulty_val.value
                else:
                    difficulty_str = str(difficulty_val) if difficulty_val is not None else ''

                status_val = paper_dict.get('status', '')
                status_str = str(status_val) if status_val is not None else ''


                data_to_export.append({
                    "试卷ID": str(paper_dict.get('paper_id', '')),
                    "用户ID": paper_dict.get('user_uid', ''),
                    "难度": difficulty_str,
                    "状态": status_str,
                    "总得分": paper_dict.get('total_score_obtained', ''),
                    "百分制得分": f"{paper_dict.get('score_percentage'):.2f}" if paper_dict.get('score_percentage') is not None else '',
                    "通过状态": pass_status_str,
                    "创建时间": paper_dict.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if paper_dict.get('created_at') else '',
                    "完成时间": paper_dict.get('completed_at').strftime('%Y-%m-%d %H:%M:%S') if paper_dict.get('completed_at') else '',
                })

            headers = ["试卷ID", "用户ID", "难度", "状态", "总得分", "百分制得分", "通过状态", "创建时间", "完成时间"]
            current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"试卷列表_{current_time}.{export_format}"

            if export_format == "csv":
                _admin_routes_logger.info(f"准备导出试卷列表到 CSV 文件: {filename}")
                return data_to_csv(data_list=data_to_export, headers=headers, filename=filename)
            elif export_format == "xlsx":
                _admin_routes_logger.info(f"准备导出试卷列表到 XLSX 文件: {filename}")
                return data_to_xlsx(data_list=data_to_export, headers=headers, filename=filename)

        if not all_papers_data and skip > 0:
             _admin_routes_logger.info(f"试卷列表查询结果为空 (skip={skip}, limit={limit}, filters applied).")

        return [PaperAdminView(**paper_data) for paper_data in all_papers_data]

    except Exception as e:
        _admin_routes_logger.error(f"管理员获取试卷列表时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取试卷列表时发生错误: {str(e)}") from e

@admin_router.get("/papers/{paper_id}", response_model=PaperFullDetailModel, summary="管理员获取特定试卷的完整信息")
async def admin_get_paper_detail(request: Request, paper_id: str = Path(..., description="要获取详情的试卷ID（UUID格式）")):
    _admin_routes_logger.info(f"管理员请求试卷 '{paper_id}' 的详细信息。")
    paper_data = await paper_crud.admin_get_paper_detail(paper_id)
    if not paper_data:
        _admin_routes_logger.warning(f"管理员请求试卷 '{paper_id}' 失败：试卷未找到。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"试卷ID '{paper_id}' 未找到。")
    try:
        if "paper_questions" not in paper_data or not isinstance(paper_data["paper_questions"], list):
            paper_data["paper_questions"] = []
        return PaperFullDetailModel(**paper_data)
    except Exception as e:
        _admin_routes_logger.error(f"管理员获取试卷 '{paper_id}' 详情时，转换数据模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"试卷数据格式错误或不完整: {str(e)}") from e

@admin_router.delete("/papers/{paper_id}", status_code=http_status.HTTP_204_NO_CONTENT, summary="管理员删除特定试卷")
async def admin_delete_paper(request: Request, paper_id: str = Path(..., description="要删除的试卷ID (UUID格式)")):
    _admin_routes_logger.info(f"管理员尝试删除试卷 '{paper_id}'。")
    deleted = await paper_crud.admin_delete_paper(paper_id)
    if not deleted:
        _admin_routes_logger.warning(f"管理员删除试卷 '{paper_id}' 失败：试卷未找到。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"试卷ID '{paper_id}' 未找到，无法删除。")
    _admin_routes_logger.info(f"管理员已成功删除试卷: {paper_id}。")
    return None
# endregion 管理员试卷管理API端点结束

# region 管理员题库管理API端点 (Admin Question Bank Management API)
@admin_router.get("/question-banks", response_model=List[LibraryIndexItem], summary="管理员获取所有题库的元数据列表")
async def admin_get_all_qbank_metadata(request: Request):
    _admin_routes_logger.info("管理员请求获取所有题库的元数据。")
    try:
        metadata_list = await qb_crud.get_all_library_metadatas()
        return metadata_list
    except Exception as e:
        _admin_routes_logger.error(f"管理员获取题库元数据列表时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取题库元数据列表时发生错误: {str(e)}")

@admin_router.get("/question-banks/{difficulty_id}/content", response_model=QuestionBank, summary="管理员获取特定难度题库的完整内容")
async def admin_get_question_bank_content(request: Request, difficulty_id: DifficultyLevel = Path(..., description="要获取内容的题库难度ID")):
    _admin_routes_logger.info(f"管理员请求获取难度为 '{difficulty_id.value}' 的题库内容。")
    try:
        full_bank = await qb_crud.get_question_bank_with_content(difficulty_id)
        if not full_bank:
            _admin_routes_logger.warning(f"管理员请求难度 '{difficulty_id.value}' 的题库内容失败：题库未找到或为空。")
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"难度为 '{difficulty_id.value}' 的题库未加载或不存在。")
        return full_bank
    except HTTPException:
        raise
    except Exception as e:
        _admin_routes_logger.error(f"管理员获取题库 '{difficulty_id.value}' 内容时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取题库 '{difficulty_id.value}' 内容时发生服务器错误。") from e

@admin_router.post("/question-banks/{difficulty_id}/questions", response_model=QuestionModel, status_code=http_status.HTTP_201_CREATED, summary="管理员向特定题库添加新题目")
async def admin_add_question_to_bank(request: Request, question: QuestionModel, difficulty_id: DifficultyLevel = Path(..., description="要添加题目的题库难度ID")):
    _admin_routes_logger.info(f"管理员尝试向题库 '{difficulty_id.value}' 添加新题目: {question.body[:50]}...")
    try:
        added_question = await qb_crud.add_question_to_bank(difficulty_id, question)
        if not added_question:
            _admin_routes_logger.error(f"管理员向题库 '{difficulty_id.value}' 添加题目失败（CRUD层返回None）。")
            raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="添加题目到题库失败，但CRUD未明确报告错误原因。")
        _admin_routes_logger.info(f"管理员已成功向题库 '{difficulty_id.value}' 添加新题目。")
        return added_question
    except ValueError as ve:
        _admin_routes_logger.warning(f"向题库 '{difficulty_id.value}' 添加题目失败: {ve}")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        _admin_routes_logger.error(f"向题库 '{difficulty_id.value}' 添加题目时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"向题库 '{difficulty_id.value}' 添加题目时发生服务器错误。")

@admin_router.delete("/question-banks/{difficulty_id}/questions", status_code=http_status.HTTP_204_NO_CONTENT, summary="管理员从特定题库删除题目")
async def admin_delete_question_from_bank(request: Request, difficulty_id: DifficultyLevel = Path(..., description="要删除题目的题库难度ID"), question_index: int = Query(..., alias="index", ge=0)):
    _admin_routes_logger.info(f"管理员尝试从题库 '{difficulty_id.value}' 删除索引为 {question_index} 的题目。")
    try:
        deleted_question_data = await qb_crud.delete_question_from_bank(difficulty_id, question_index)
        if deleted_question_data is None:
            _admin_routes_logger.warning(f"管理员删除题库 '{difficulty_id.value}' 索引 {question_index} 的题目失败（可能索引无效或题目不存在）。")
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"在题库 '{difficulty_id.value}' 中未找到索引为 {question_index} 的题目，或题库本身不存在。")
        deleted_body = deleted_question_data.get("body", "N/A")
        _admin_routes_logger.info(f"管理员已成功从题库 '{difficulty_id.value}' 删除索引为 {question_index} 的题目: {deleted_body[:50]}...")
        return None
    except ValueError as ve:
        _admin_routes_logger.warning(f"从题库 '{difficulty_id.value}' 删除题目失败: {ve}")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        _admin_routes_logger.error(f"从题库 '{difficulty_id.value}' 删除题目时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"从题库 '{difficulty_id.value}' 删除题目时发生服务器错误。")
# endregion 管理员题库管理API端点结束

# region 管理员阅卷接口 (Admin Grading API)
grading_router = APIRouter(
    prefix="/grading",
    tags=["阅卷接口 (Grading)"],
    dependencies=[Depends(require_admin)]
)

@grading_router.get(
    "/pending-papers",
    response_model=List[PendingGradingPaperItem],
    summary="获取待人工批阅的试卷列表",
    description="返回一个试卷列表，这些试卷包含主观题且有题目等待人工批阅 (pending_manual_grading_count > 0)。"
)
async def get_papers_pending_grading(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=200, description="返回的最大记录数")
):
    try:
        papers_data = await paper_crud.get_papers_pending_manual_grading(skip=skip, limit=limit)
        return [PendingGradingPaperItem(**p) for p in papers_data]
    except Exception as e:
        _admin_routes_logger.error(f"获取待批阅试卷列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="获取待批阅试卷列表失败。")

@grading_router.get(
    "/papers/{paper_id}/subjective-questions",
    response_model=List[SubjectiveQuestionForGrading],
    summary="获取试卷中待批阅的主观题详情",
    description="返回指定试卷中所有主观题的列表，包含题干、学生答案、参考答案、评分标准及当前批阅状态。"
)
async def get_subjective_questions_for_grading(
    paper_id: UUID = Path(..., description="试卷ID")
):
    paper_data = await paper_crud.admin_get_paper_detail(str(paper_id))
    if not paper_data:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"试卷ID '{paper_id}' 未找到。")

    subjective_questions_for_grading = []
    for q_internal in paper_data.get("paper_questions", []):
        if q_internal.get("question_type") == QuestionTypeEnum.ESSAY_QUESTION.value:
            subjective_questions_for_grading.append(SubjectiveQuestionForGrading(**q_internal))

    if not subjective_questions_for_grading:
         _admin_routes_logger.info(f"试卷 '{paper_id}' 不包含主观题或主观题数据缺失。")

    return subjective_questions_for_grading

@grading_router.post(
    "/papers/{paper_id}/questions/{question_internal_id}/grade",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="提交单个主观题的批阅结果",
    description="接收阅卷员对特定试卷中特定主观题的评分和评语，并更新到系统中。成功后，如果试卷所有题目均已批改，将触发最终状态计算。"
)
async def grade_single_subjective_question(
    payload: GradeSubmissionPayload,
    paper_id: UUID = Path(..., description="试卷ID"),
    question_internal_id: str = Path(..., description="试卷中题目的内部唯一ID"),
):
    try:
        success = await paper_crud.grade_subjective_question(
            paper_id=paper_id,
            question_internal_id=question_internal_id,
            manual_score=payload.manual_score,
            teacher_comment=payload.teacher_comment
        )
        if not success:
            raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新题目批阅结果失败。")

        asyncio.create_task(paper_crud.finalize_paper_grading_if_ready(paper_id))

        return None
    except ValueError as ve:
        _admin_routes_logger.warning(f"批改主观题失败 (paper_id: {paper_id}, q_id: {question_internal_id}): {ve}")
        if "未找到" in str(ve):
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(ve))
        else:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        _admin_routes_logger.error(f"批改主观题时发生意外错误 (paper_id: {paper_id}, q_id: {question_internal_id}): {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="批改主观题时发生意外错误。")

admin_router.include_router(grading_router)
# endregion 管理员阅卷接口结束

# region 管理员Token管理API端点 (Admin Token Management API)
token_admin_router = APIRouter(
    prefix="/tokens",
    tags=["管理接口 - Token管理 (Admin - Token Management)"],
    dependencies=[Depends(RequireTags({UserTag.MANAGER}))]
)

@token_admin_router.get(
    "/",
    response_model=List[Dict[str, Any]],
    summary="管理员获取当前所有活动Token的摘要列表",
    description="获取系统中所有当前活动（未过期）用户访问Token的摘要信息列表。此列表主要用于监控和审计目的。"
)
async def admin_list_active_tokens(request: Request):
    actor_uid = getattr(request.state, "current_user_uid", "unknown_admin")
    client_ip = get_client_ip_from_request(request)
    _admin_routes_logger.info(f"管理员 '{actor_uid}' (IP: {client_ip}) 请求获取所有活动Token的列表。")

    active_tokens_info = await get_all_active_token_info()

    await audit_logger_service.log_event(
        action_type="ADMIN_LIST_TOKENS", status="SUCCESS",
        actor_uid=actor_uid, actor_ip=client_ip,
        details={"message": f"管理员查看了活动Token列表 (共 {len(active_tokens_info)} 个)"}
    )
    return active_tokens_info

@token_admin_router.delete(
    "/user/{user_uid}",
    summary="管理员吊销特定用户的所有活动Token",
    description="立即吊销（删除）指定用户ID的所有活动访问Token。此操作会强制该用户在所有设备上登出。"
)
async def admin_invalidate_user_tokens(user_uid: str = Path(..., description="要吊销其Token的用户的UID"), request: Request = Depends(lambda r: r)):
    actor_uid = getattr(request.state, "current_user_uid", "unknown_admin")
    client_ip = get_client_ip_from_request(request)
    _admin_routes_logger.info(f"管理员 '{actor_uid}' (IP: {client_ip}) 尝试吊销用户 '{user_uid}' 的所有Token。")

    invalidated_count = await invalidate_all_tokens_for_user(user_uid)

    _admin_routes_logger.info(f"管理员 '{actor_uid}' 为用户 '{user_uid}' 吊销了 {invalidated_count} 个Token。")
    await audit_logger_service.log_event(
        action_type="ADMIN_INVALIDATE_USER_TOKENS", status="SUCCESS",
        actor_uid=actor_uid, actor_ip=client_ip,
        target_resource_type="USER_TOKENS", target_resource_id=user_uid,
        details={"message": f"管理员吊销了用户 '{user_uid}' 的 {invalidated_count} 个Token。", "count": invalidated_count}
    )
    return {
        "message": f"成功为用户 '{user_uid}' 吊销了 {invalidated_count} 个Token。",
        "invalidated_count": invalidated_count
    }

@token_admin_router.delete(
    "/{token_string}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="管理员吊销指定的单个活动Token",
    description="立即吊销（删除）指定的单个活动访问Token。管理员需要提供完整的Token字符串。请谨慎使用，确保Token字符串的准确性。"
)
async def admin_invalidate_single_token(token_string: str = Path(..., description="要吊销的完整Token字符串"), request: Request = Depends(lambda r: r)):
    actor_uid = getattr(request.state, "current_user_uid", "unknown_admin")
    client_ip = get_client_ip_from_request(request)
    token_prefix_for_log = token_string[:8] + "..."
    _admin_routes_logger.info(f"管理员 '{actor_uid}' (IP: {client_ip}) 尝试吊销单个Token (前缀: {token_prefix_for_log})。")

    await invalidate_token(token_string)

    await audit_logger_service.log_event(
        action_type="ADMIN_INVALIDATE_SINGLE_TOKEN", status="SUCCESS",
        actor_uid=actor_uid, actor_ip=client_ip,
        target_resource_type="TOKEN", target_resource_id=token_prefix_for_log,
        details={"message": "管理员吊销了单个Token"}
    )
    return None

admin_router.include_router(token_admin_router)
# endregion 管理员Token管理API端点结束

# region 管理员审计日志查看API端点 (Admin Audit Log Viewing API)

def _parse_log_timestamp(timestamp_str: str) -> Optional[datetime]:
    """安全地将ISO格式的时间戳字符串解析为datetime对象。"""
    if not timestamp_str:
        return None
    try:
        return datetime.fromisoformat(timestamp_str)
    except ValueError:
        try:
            _admin_routes_logger.warning(f"无法解析审计日志中的时间戳字符串: '{timestamp_str}'")
            return None
        except Exception:
             _admin_routes_logger.warning(f"解析审计日志时间戳时发生未知错误: '{timestamp_str}'")
             return None


@admin_router.get(
    "/audit-logs",
    response_model=List[Dict[str, Any]],
    summary="管理员查看审计日志",
    description="获取应用审计日志，支持分页和筛选 (操作者UID, 操作类型, 时间范围)。日志默认按时间倒序（最新在前）。"
)
async def admin_view_audit_logs(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    per_page: int = Query(50, ge=1, le=200, description="每页条目数"),
    actor_uid_filter: Optional[str] = Query(None, alias="actor_uid", description="按操作者UID筛选"),
    action_type_filter: Optional[str] = Query(None, alias="action_type", description="按操作类型筛选"),
    start_time_filter: Optional[datetime] = Query(None, alias="start_time", description="起始时间筛选 (ISO格式)"),
    end_time_filter: Optional[datetime] = Query(None, alias="end_time", description="结束时间筛选 (ISO格式)")
):
    log_file_path = settings.audit_log_file_path
    if not Path(log_file_path).exists():
        _admin_routes_logger.info(f"审计日志文件 '{log_file_path}' 未找到。")
        return []

    all_log_entries: List[Dict[str, Any]] = []
    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        log_entry_dict = json.loads(line)
                        all_log_entries.append(log_entry_dict)
                    except json.JSONDecodeError:
                        _admin_routes_logger.warning(f"无法解析的审计日志行 (JSON无效): '{line[:200]}...'")
                        continue
    except IOError as e:
        _admin_routes_logger.error(f"读取审计日志文件 '{log_file_path}' 时发生IO错误: {e}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="读取审计日志失败。")

    filtered_logs = []
    for entry in all_log_entries:
        log_timestamp_str = entry.get("timestamp")
        log_datetime = _parse_log_timestamp(log_timestamp_str)

        if log_datetime is None and (start_time_filter or end_time_filter):
            _admin_routes_logger.debug(f"跳过时间范围筛选无效时间戳的日志条目: event_id={entry.get('event_id')}")
            continue

        if actor_uid_filter and entry.get("actor_uid") != actor_uid_filter:
            continue
        if action_type_filter and entry.get("action_type") != action_type_filter:
            continue
        if start_time_filter and (log_datetime is None or log_datetime < start_time_filter):
            continue
        if end_time_filter and (log_datetime is None or log_datetime > end_time_filter):
            continue

        filtered_logs.append(entry)
    try:
        filtered_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    except Exception as e_sort:
        _admin_routes_logger.error(f"排序审计日志时出错: {e_sort}. 日志可能未按时间排序。")

    start_index = (page - 1) * per_page
    end_index = start_index + per_page

    paginated_logs = filtered_logs[start_index:end_index]

    return paginated_logs

# endregion 管理员审计日志查看API端点结束

__all__ = ["admin_router"]

if __name__ == "__main__":
    _admin_routes_logger.info(
        f"模块 {__name__} 定义了管理员相关的API路由，不应直接执行。它应被 FastAPI 应用导入。"
    )
    print(
        f"模块 {__name__} 定义了管理员相关的API路由，不应直接执行。它应被 FastAPI 应用导入。"
    )
