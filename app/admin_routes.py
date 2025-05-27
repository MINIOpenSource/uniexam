# -*- coding: utf-8 -*-
# region 模块导入
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status

# 使用相对导入从同级或父级包导入
from .core.security import require_admin # 依赖项，确保用户有admin标签
from .core.config import settings, DifficultyLevel # 全局配置和难度枚举
from .models.user_models import UserPublicProfile, AdminUserUpdate, UserInDB # 用户模型
from .models.paper_models import PaperAdminView, PaperFullDetailModel # 试卷模型
from .models.qb_models import QuestionModel, LibraryIndexItem, QuestionBank # 题库模型
from .models.config_models import SettingsResponseModel, SettingsUpdatePayload # 配置模型 (需要创建)

# CRUD操作实例将在主应用 (main.py) 中创建并作为依赖项传入，或通过全局变量访问
# 为避免循环导入，这里假设它们可以通过某种方式在运行时获得
# 例如，通过 Depends 获取，或者从一个集中的地方导入 (如 app.main)
# from ..main import user_crud, paper_crud, qb_crud, settings_crud
# 更好的方式是通过依赖注入或在 main.py 中将 crud 实例附加到 app.state

# 暂时通过全局变量方式获取 (在 main.py 中定义这些实例)
# from ..main import user_crud_instance, paper_crud_instance, qb_crud_instance, settings_crud_instance
# 为了模块的独立性，更好的做法是在路由函数中通过 Depends 获取 CRUD 实例
# 但为了简化当前步骤，我们将假设这些实例在 app.crud.__init__.py 中被正确初始化并可访问
# (实际项目中，应使用更健壮的依赖注入模式)
from .crud import user_crud_instance as user_crud, paper_crud_instance as paper_crud, qb_crud_instance as qb_crud, settings_crud_instance as settings_crud # 假设这些实例在 __init__.py 中暴露或直接导入
# endregion

# region 全局变量与初始化
_admin_routes_logger = logging.getLogger(__name__)

admin_router = APIRouter(
    prefix="/admin",  # 所有此路由下的端点都以 /admin 开头
    tags=["Admin"],  # API文档中的标签分组
    dependencies=[Depends(require_admin)],  # 应用Token认证和admin标签检查到所有路由
    responses={
        http_status.HTTP_401_UNAUTHORIZED: {"description": "Token missing or invalid"},
        http_status.HTTP_403_FORBIDDEN: {"description": "Insufficient permissions (not an admin)"}
    }
)
# endregion

# region Admin Settings API 端点
@admin_router.get(
    "/settings",
    response_model=SettingsResponseModel, # SettingsResponseModel 需要在 config_models.py 中定义
    summary="获取当前应用配置"
)
async def admin_get_settings():
    """
    获取当前应用的配置信息 (settings.json 的内容，可能不包含.env覆盖项)。
    实际生效的配置是内存中的 `settings` 对象，它已合并.env。
    此接口返回 `settings.json` 的原始内容，用于展示和编辑。
    """
    _admin_routes_logger.info("Admin请求获取应用配置。")
    # settings_crud 实例应该在 main.py 中初始化并可访问
    current_settings_from_file = settings_crud.get_current_settings_from_file()
    # 注意：返回的是 SettingsResponseModel，它应该只包含可以被admin修改的字段
    # 或者，如果Settings模型本身就是用于settings.json的，可以直接返回settings对象
    # 但更安全的做法是定义一个专门的响应模型。
    # 为简单起见，如果 SettingsResponseModel 与 Settings 结构一致（排除敏感或不可改字段）
    # 我们可以尝试直接用全局 settings，但 get_current_settings_from_file 更准确反映文件内容
    
    # SettingsResponseModel 应与 Settings 结构类似，但不包含如 data_dir 等内部字段
    # 并且，它应该反映 settings.json 的内容，而不是内存中被 .env 覆盖后的内容
    # 所以，直接用 get_current_settings_from_file() 返回的字典创建 SettingsResponseModel
    try:
        # 确保 SettingsResponseModel 能够从字典初始化
        return SettingsResponseModel(**current_settings_from_file)
    except Exception as e: # Pydantic ValidationError
        _admin_routes_logger.error(f"将文件配置转换为SettingsResponseModel时出错: {e}")
        # 返回一个表示错误的默认或空配置
        return SettingsResponseModel()


@admin_router.post(
    "/settings",
    response_model=SettingsResponseModel, # 返回更新后的配置 (settings.json 的目标状态)
    summary="更新应用配置"
)
async def admin_update_settings(payload: SettingsUpdatePayload): # SettingsUpdatePayload 需定义
    """
    更新应用的配置项 (写入 settings.json 并重新加载全局配置)。
    注意：.env 文件中的配置项优先级更高，不会被此接口的更新覆盖内存中的实际生效值，
    但 settings.json 文件会被更新。
    """
    _admin_routes_logger.info(f"Admin尝试更新应用配置，数据: {payload.model_dump_json(indent=2)}")
    # from ..main import settings_crud_instance
    try:
        # payload.model_dump(exclude_unset=True)确保只传递实际提供的字段
        updated_settings_obj = await settings_crud.update_settings_file_and_reload(
            payload.model_dump(exclude_unset=True)
        )
        # 返回更新后，从文件重新加载（并被.env覆盖）的配置
        # 或者，更准确地返回被写入到 settings.json 的目标状态
        # 这里我们返回实际写入 settings.json 的内容（payload 应用到现有文件内容后）
        settings_from_file_after_update = settings_crud.get_current_settings_from_file()
        return SettingsResponseModel(**settings_from_file_after_update)

    except ValueError as e_val: # 来自 update_and_persist_settings 的验证错误
        _admin_routes_logger.warning(f"Admin更新配置失败 (数据验证错误): {e_val}")
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e_val))
    except IOError as e_io:
        _admin_routes_logger.error(f"Admin更新配置失败 (文件写入错误): {e_io}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to write settings to file.")
    except RuntimeError as e_rt: # 其他 update_and_persist_settings 抛出的错误
        _admin_routes_logger.error(f"Admin更新配置失败 (运行时错误): {e_rt}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e_rt))
    except Exception as e:
        _admin_routes_logger.error(f"Admin更新配置时发生未知错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred while updating settings.")
# endregion

# region Admin User Management API 端点
@admin_router.get(
    "/users",
    response_model=List[UserPublicProfile], # 返回用户公开信息列表
    summary="获取所有用户列表 (Admin)"
)
async def admin_get_all_users(skip: int = 0, limit: int = 100):
    """管理员获取系统中的所有用户列表（分页）。"""
    # from ..main import user_crud_instance
    users_in_db = user_crud.admin_get_all_users(skip=skip, limit=limit)
    # 将 UserInDB 转换为 UserPublicProfile 以隐藏密码等敏感信息
    return [UserPublicProfile.model_validate(user) for user in users_in_db]

@admin_router.get(
    "/users/{user_uid}",
    response_model=UserPublicProfile, # 或更详细的Admin特定用户视图
    summary="获取特定用户详情 (Admin)"
)
async def admin_get_user(user_uid: str):
    """管理员获取指定UID用户的详细信息。"""
    # from ..main import user_crud_instance
    user = user_crud.get_user_by_uid(user_uid)
    if not user:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserPublicProfile.model_validate(user)

@admin_router.put(
    "/users/{user_uid}",
    response_model=UserPublicProfile,
    summary="更新特定用户信息 (Admin)"
)
async def admin_update_user_info(user_uid: str, update_payload: AdminUserUpdate):
    """
    管理员更新指定UID用户的信息，包括昵称、邮箱、QQ、标签和可选的密码重置。
    """
    # from ..main import user_crud_instance
    updated_user = await user_crud.admin_update_user(user_uid, update_payload)
    if not updated_user:
        # 原因可能是用户不存在，或更新数据验证失败 (已在CRUD层处理并记录日志)
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="User not found or update failed")
    
    # 如果更新了密码，可能需要让用户的现有Token失效，但这需要更复杂的Token管理
    # 目前简单返回更新后的用户信息
    return UserPublicProfile.model_validate(updated_user)

# TODO: 可能需要一个专门的接口来“封禁”或“解封”用户，即修改其BANNED标签
# 例如 POST /admin/users/{user_uid}/ban 和 POST /admin/users/{user_uid}/unban

# endregion

# region Admin Paper Management API 端点 (与之前类似，但使用Token认证)
@admin_router.get("/paper/all", response_model=List[PaperAdminView], summary="获取所有试卷摘要")
def admin_get_all_papers_summary(skip: int = 0, limit: int = 100):
    """获取内存中所有试卷的摘要信息列表，按创建时间倒序排列。"""
    # from ..main import paper_crud_instance
    try:
        all_papers_data = paper_crud.admin_get_all_papers_summary_from_memory(skip, limit)
        summaries = []
        for paper_data in all_papers_data:
            count = len(paper_data.get("paper_questions", []))
            submitted_card = paper_data.get("submitted_answers_card")
            finished_count = len(submitted_card) if isinstance(submitted_card, list) else None
            correct_count = paper_data.get("score") # score 即为正确题数

            summaries.append(PaperAdminView(
                paper_id=str(paper_data.get("paper_id", "N/A")),
                user_uid=paper_data.get("user_uid"),
                creation_time_utc=paper_data.get("creation_time_utc", "N/A"),
                creation_ip=paper_data.get("creation_ip", "N/A"),
                difficulty=paper_data.get("difficulty"),
                count=count,
                finished_count=finished_count,
                correct_count=correct_count,
                score=paper_data.get("score"),
                submission_time_utc=paper_data.get("submission_time_utc"),
                submission_ip=paper_data.get("submission_ip"),
                pass_status=paper_data.get("pass_status"),
                passcode=paper_data.get("passcode"),
                last_update_time_utc=paper_data.get("last_update_time_utc"),
                last_update_ip=paper_data.get("last_update_ip")
            ))
        return summaries
    except Exception as e:
        _admin_routes_logger.error(f"[AdminAPI] /paper/all: 获取试卷列表时发生意外错误: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error fetching paper list: {str(e)}")

@admin_router.get("/paper/", response_model=PaperFullDetailModel, summary="获取指定试卷的详细信息")
def admin_get_paper_detail(paper_id: str = Query(..., description="要获取详情的试卷ID")):
    """获取内存中指定 `paper_id` 的试卷的完整详细信息。"""
    # from ..main import paper_crud_instance
    paper_data = paper_crud.admin_get_paper_detail_from_memory(paper_id)
    if not paper_data:
        _admin_routes_logger.warning(f"[AdminAPI] /paper/?paper_id={paper_id}: 试卷未找到。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Paper ID '{paper_id}' not found.")
    try:
        if "paper_questions" not in paper_data or not isinstance(paper_data["paper_questions"], list):
            paper_data["paper_questions"] = [] 
        return PaperFullDetailModel(**paper_data)
    except Exception as e:
        _admin_routes_logger.error(f"[AdminAPI] /paper/?paper_id={paper_id}: 转换试卷数据为详细模型时出错: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Paper data format error: {str(e)}")

@admin_router.delete("/paper/", status_code=http_status.HTTP_200_OK, summary="删除指定的试卷")
def admin_delete_paper(paper_id: str = Query(..., description="要删除的试卷ID")):
    """从内存中删除指定 `paper_id` 的试卷记录。更改将在下次持久化时写入文件。"""
    # from ..main import paper_crud_instance
    deleted = paper_crud.admin_delete_paper_from_memory(paper_id)
    if not deleted:
        _admin_routes_logger.warning(f"[AdminAPI] DELETE /paper/?paper_id={paper_id}: 试卷未找到，无法删除。")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Paper ID '{paper_id}' not found, cannot delete.")
    _admin_routes_logger.info(f"[AdminAPI] 已删除试卷 (内存): {paper_id}。")
    return {"message": f"Paper {paper_id} successfully deleted from memory."}
# endregion

# region Admin Question Bank Management API 端点
@admin_router.get("/question/", response_model=List[QuestionModel], summary="获取指定难度的题库")
async def admin_get_question_bank(difficulty: DifficultyLevel = Query(..., description="题库难度")):
    """获取指定难度题库的所有题目。"""
    # from ..main import qb_crud_instance
    full_bank = await qb_crud.get_question_bank_with_content(difficulty)
    
    if not full_bank or not full_bank.questions:
        _admin_routes_logger.error(
            f"[AdminAPI] /question/?difficulty={difficulty.value}: "
            f"难度题库内容未加载或为空。"
        )
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Question bank for difficulty '{difficulty.value}' not loaded or does not exist.")

    try:
        # full_bank.questions 已经是 List[QuestionModel]
        return full_bank.questions
    except Exception as e:
        _admin_routes_logger.error(f"[AdminAPI] /question/?difficulty={difficulty.value}: 转换题库数据时出错: {e}", exc_info=True)
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Question bank data format error.")

@admin_router.post("/question/", status_code=http_status.HTTP_201_CREATED, response_model=QuestionModel, summary="为指定难度的题库添加题目")
async def admin_add_question_to_bank(question: QuestionModel, difficulty: DifficultyLevel = Query(..., description="题库难度")):
    """向指定难度的题库JSON文件添加一个新题目，并触发内存中题库的重新加载。"""
    # from ..main import qb_crud_instance
    added_question = await qb_crud.add_question_to_bank(difficulty, question)
    if not added_question:
        _admin_routes_logger.error(f"[AdminAPI] 向题库 '{difficulty.value}' 添加题目失败。")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add question to bank.")
    
    _admin_routes_logger.info(f"[AdminAPI] 已向题库 '{difficulty.value}' 添加新题目: {question.body[:50]}...")
    return added_question

@admin_router.delete("/question/", status_code=http_status.HTTP_200_OK, summary="删除指定题库的指定题目")
async def admin_delete_question_from_bank(
    difficulty: DifficultyLevel = Query(..., description="题库难度"),
    _index: int = Query(..., alias="index", description="要删除的题目索引 (从0开始)")
):
    """根据索引从指定难度的题库JSON文件中删除一个题目，并触发内存中题库的重新加载。"""
    # from ..main import qb_crud_instance
    deleted_question_data = await qb_crud.delete_question_from_bank(difficulty, _index)
    if deleted_question_data is None: # None 表示删除失败（例如索引无效或文件操作错误）
        # qb_crud 内部已记录具体错误
        # 此处需要判断是404还是500，但qb_crud不直接抛HTTPException
        # 假设如果返回None，通常是索引问题或文件未找到
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Question at index {_index} in bank '{difficulty.value}' not found or deletion failed.")

    deleted_body = deleted_question_data.get("body", "N/A")
    _admin_routes_logger.info(f"[AdminAPI] 已从题库 '{difficulty.value}' 删除索引为 {_index} 的题目: {deleted_body[:50]}...")
    return {
        "message": f"Successfully deleted question at index {_index} from bank '{difficulty.value}'.",
        "deleted_question_body": deleted_body
    }
# endregion
