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
# region 模块导入
import logging
import asyncio # Added for background task in grading
from typing import List, Optional
from uuid import UUID # Added for paper_id type hint

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    status as http_status,
)

from .core.config import DifficultyLevel
from .core.security import require_admin
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
from .models.enums import QuestionTypeEnum # Already imported in previous version, ensure it stays
from .models.paper_models import (
    PaperAdminView,
    PaperFullDetailModel,
    PendingGradingPaperItem,      # New model for grading
    SubjectiveQuestionForGrading, # New model for grading
    GradeSubmissionPayload,       # New model for grading
)
from .models.qb_models import (
    LibraryIndexItem,
    QuestionBank,
    QuestionModel,
)
from .models.user_models import (
    AdminUserUpdate,
    UserPublicProfile,
    UserTag, # Required for RequireTags if we use GRADER, though current plan is ADMIN only for grading
)

# endregion

# region 全局变量与初始化
_admin_routes_logger = logging.getLogger(__name__)

admin_router = APIRouter(
    tags=["管理员接口 (Admin)"],
    dependencies=[Depends(require_admin)],
    responses={
        http_status.HTTP_401_UNAUTHORIZED: {"description": "Token缺失或无效 (Unauthorized)"},
        http_status.HTTP_403_FORBIDDEN: {"description": "权限不足 (非管理员用户) (Forbidden)"},
    },
)
# endregion


# region Admin Settings API 端点
@admin_router.get(
    "/settings",
    response_model=SettingsResponseModel,
    summary="获取当前系统配置",
    description="管理员获取当前应用的主要配置项信息...", # Truncated for brevity
)
async def admin_get_settings():
    _admin_routes_logger.info("管理员请求获取应用配置。")
    current_settings_from_file = settings_crud.get_current_settings_from_file()
    try:
        return SettingsResponseModel(**current_settings_from_file)
    except Exception as e:
        _admin_routes_logger.error(f"将文件配置转换为SettingsResponseModel时出错: {e}")
        return SettingsResponseModel()

@admin_router.post(
    "/settings",
    response_model=SettingsResponseModel,
    summary="更新系统配置",
    description="管理员更新应用的部分或全部可配置项...", # Truncated for brevity
)
async def admin_update_settings(payload: SettingsUpdatePayload):
    _admin_routes_logger.info(f"管理员尝试更新应用配置，数据: {payload.model_dump_json(indent=2)}")
    try:
        await settings_crud.update_settings_file_and_reload(payload.model_dump(exclude_unset=True))
        settings_from_file_after_update = settings_crud.get_current_settings_from_file()
        _admin_routes_logger.info("应用配置已成功更新并重新加载。")
        return SettingsResponseModel(**settings_from_file_after_update)
    except ValueError as e_val:
        _admin_routes_logger.warning(f"管理员更新配置失败 (数据验证错误): {e_val}")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e_val)) from e_val
    except IOError as e_io:
        _admin_routes_logger.error(f"管理员更新配置失败 (文件写入错误): {e_io}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="配置文件写入失败。") from e_io
    except RuntimeError as e_rt:
        _admin_routes_logger.error(f"管理员更新配置失败 (运行时错误): {e_rt}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e_rt)) from e_rt
    except Exception as e:
        _admin_routes_logger.error(f"管理员更新配置时发生未知错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新配置时发生意外错误。") from e
# endregion

# region Admin User Management API 端点
@admin_router.get("/users", response_model=List[UserPublicProfile], summary="管理员获取用户列表")
async def admin_get_all_users(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
    _admin_routes_logger.info(f"管理员请求用户列表，skip={skip}, limit={limit}。")
    users_in_db = await user_crud.admin_get_all_users(skip=skip, limit=limit)
    return [UserPublicProfile.model_validate(user) for user in users_in_db]

@admin_router.get("/users/{user_uid}", response_model=UserPublicProfile, summary="管理员获取特定用户信息")
async def admin_get_user(*, user_uid: str = Path(..., description="要获取详情的用户的UID")):
    _admin_routes_logger.info(f"管理员请求用户 '{user_uid}' 的详细信息。")
    user = await user_crud.get_user_by_uid(user_uid)
    if not user:
        _admin_routes_logger.warning(f"管理员请求用户 '{user_uid}' 失败：用户未找到。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="用户未找到")
    return UserPublicProfile.model_validate(user)

@admin_router.put("/users/{user_uid}", response_model=UserPublicProfile, summary="管理员更新特定用户信息")
async def admin_update_user_info(*, user_uid: str = Path(..., description="要更新信息的用户的UID"), update_payload: AdminUserUpdate):
    _admin_routes_logger.info(f"管理员尝试更新用户 '{user_uid}' 的信息，数据: {update_payload.model_dump_json(exclude_none=True)}")
    updated_user = await user_crud.admin_update_user(user_uid, update_payload)
    if not updated_user:
        _admin_routes_logger.warning(f"管理员更新用户 '{user_uid}' 失败：用户未找到或更新无效。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="用户未找到或更新失败。")
    _admin_routes_logger.info(f"管理员成功更新用户 '{user_uid}' 的信息。")
    return UserPublicProfile.model_validate(updated_user)
# endregion

# region Admin Paper Management API 端点
@admin_router.get("/papers", response_model=List[PaperAdminView], summary="管理员获取所有试卷摘要列表")
async def admin_get_all_papers_summary(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
    _admin_routes_logger.info(f"管理员请求试卷摘要列表，skip={skip}, limit={limit}。")
    try:
        all_papers_data = await paper_crud.admin_get_all_papers_summary(skip, limit)
        return [PaperAdminView(**paper_data) for paper_data in all_papers_data]
    except Exception as e:
        _admin_routes_logger.error(f"管理员获取试卷列表时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取试卷列表时发生错误: {str(e)}") from e

@admin_router.get("/papers/{paper_id}", response_model=PaperFullDetailModel, summary="管理员获取特定试卷的完整信息")
async def admin_get_paper_detail(paper_id: str = Path(..., description="要获取详情的试卷ID (UUID格式)")):
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
async def admin_delete_paper(paper_id: str = Path(..., description="要删除的试卷ID (UUID格式)")):
    _admin_routes_logger.info(f"管理员尝试删除试卷 '{paper_id}'。")
    deleted = await paper_crud.admin_delete_paper(paper_id)
    if not deleted:
        _admin_routes_logger.warning(f"管理员删除试卷 '{paper_id}' 失败：试卷未找到。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"试卷ID '{paper_id}' 未找到，无法删除。")
    _admin_routes_logger.info(f"管理员已成功删除试卷: {paper_id}。")
    return None
# endregion

# region Admin Question Bank Management API 端点
@admin_router.get("/question-banks", response_model=List[LibraryIndexItem], summary="管理员获取所有题库的元数据列表")
async def admin_get_all_qbank_metadata():
    _admin_routes_logger.info("管理员请求获取所有题库的元数据。")
    try:
        metadata_list = await qb_crud.get_all_library_metadatas()
        return metadata_list
    except Exception as e:
        _admin_routes_logger.error(f"管理员获取题库元数据列表时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取题库元数据列表时发生错误: {str(e)}")

@admin_router.get("/question-banks/{difficulty_id}/content", response_model=QuestionBank, summary="管理员获取特定难度题库的完整内容")
async def admin_get_question_bank_content(difficulty_id: DifficultyLevel = Path(..., description="要获取内容的题库难度ID")):
    _admin_routes_logger.info(f"管理员请求获取难度为 '{difficulty_id.value}' 的题库内容。")
    try:
        full_bank = await qb_crud.get_question_bank_with_content(difficulty_id)
        if not full_bank:
            _admin_routes_logger.warning(f"管理员请求难度 '{difficulty_id.value}' 的题库内容失败：题库未找到或为空。")
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"难度为 '{difficulty_id.value}' 的题库未加载或不存在。")
        return full_bank
    except HTTPException: raise
    except Exception as e:
        _admin_routes_logger.error(f"管理员获取题库 '{difficulty_id.value}' 内容时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"获取题库 '{difficulty_id.value}' 内容时发生服务器错误。") from e

@admin_router.post("/question-banks/{difficulty_id}/questions", response_model=QuestionModel, status_code=http_status.HTTP_201_CREATED, summary="管理员向特定题库添加新题目")
async def admin_add_question_to_bank(question: QuestionModel, difficulty_id: DifficultyLevel = Path(..., description="要添加题目的题库难度ID")):
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
async def admin_delete_question_from_bank(difficulty_id: DifficultyLevel = Path(..., description="要删除题目的题库难度ID"), question_index: int = Query(..., alias="index", ge=0)):
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
# endregion

# region Admin Grading API 端点 (管理员阅卷接口)
grading_router = APIRouter(
    prefix="/grading",
    tags=["阅卷接口 (Grading)"],
    dependencies=[Depends(require_admin)] # Initially restrict to ADMIN
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
            # internal_question_id is already part of q_internal from PaperQuestionInternalDetail
            subjective_questions_for_grading.append(SubjectiveQuestionForGrading(**q_internal))

    if not subjective_questions_for_grading:
         _admin_routes_logger.info(f"试卷 '{paper_id}' 不包含主观题或主观题数据缺失。")
        # Not an error, just might be an empty list if no subjective questions or they are malformed

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
            # grade_subjective_question raises ValueError for known issues like not found,
            # so False here might indicate a repository update failure.
            raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新题目批阅结果失败。")

        # Asynchronously attempt to finalize paper grading if all subjective questions are now graded.
        # The client does not wait for this, ensuring a quick response for grading a single question.
        # The paper's status will be updated in the background if finalization occurs.
        asyncio.create_task(paper_crud.finalize_paper_grading_if_ready(paper_id))

        return None # HTTP 204
    except ValueError as ve:
        _admin_routes_logger.warning(f"批改主观题失败 (paper_id: {paper_id}, q_id: {question_internal_id}): {ve}")
        # Determine if it's a 404 (not found) or 400 (bad request, e.g. not an essay question)
        if "未找到" in str(ve):
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(ve))
        else:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        _admin_routes_logger.error(f"批改主观题时发生意外错误 (paper_id: {paper_id}, q_id: {question_internal_id}): {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="批改主观题时发生意外错误。")

admin_router.include_router(grading_router) # 将阅卷路由挂载到管理员路由下
# endregion


__all__ = ["admin_router"]

if __name__ == "__main__":
    _admin_routes_logger.info(
        f"模块 {__name__} 定义了管理员相关的API路由，不应直接执行。它应被 FastAPI 应用导入。"
    )
    print(
        f"模块 {__name__} 定义了管理员相关的API路由，不应直接执行。它应被 FastAPI 应用导入。"
    )
