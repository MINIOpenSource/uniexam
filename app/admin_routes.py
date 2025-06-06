# -*- coding: utf-8 -*-
"""
管理员后台 API 路由模块。

此模块定义了所有与管理员操作相关的API端点，例如：
- 应用配置管理 (获取、更新)
- 用户管理 (列表、详情、更新)
- 试卷管理 (列表、详情、删除)
- 题库管理 (查看题库、添加题目、删除题目)

所有此模块下的路由都需要管理员权限（通过 `require_admin` 依赖项进行验证）。
"""
# region 模块导入
import logging
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,  # 确保导入Path
    Query,
    status as http_status,
)

from .core.config import DifficultyLevel  # 全局配置和难度枚举
from .core.security import require_admin  # 依赖项，确保用户有admin标签
from .crud import (  # CRUD 操作实例导入
    paper_crud_instance as paper_crud,
    qb_crud_instance as qb_crud,
    settings_crud_instance as settings_crud,
    user_crud_instance as user_crud,
)
from .models.config_models import (  # 配置相关的Pydantic模型
    SettingsResponseModel,
    SettingsUpdatePayload,
)
from .models.paper_models import (
    PaperAdminView,
    PaperFullDetailModel,
)  # 试卷相关的Pydantic模型
from .models.qb_models import QuestionModel  # 题库相关的Pydantic模型
from .models.user_models import (
    AdminUserUpdate,
    UserPublicProfile,
)  # 用户相关的Pydantic模型

# endregion

# region 全局变量与初始化
_admin_routes_logger = logging.getLogger(__name__)  # 获取模块特定的日志记录器实例

admin_router = APIRouter(  # FastAPI APIRouter 实例，用于组织管理员相关路由
    # prefix="/admin",  # 所有此路由下的端点都以 /admin 作为URL前缀 (已在app.main中挂载时指定)
    tags=[
        "管理员接口 (Admin)"
    ],  # 在OpenAPI文档中将这些端点分组到 "管理员接口 (Admin)" 标签下
    dependencies=[
        Depends(require_admin)
    ],  # 对此路由器下的所有路由应用 `require_admin` 依赖项 (验证管理员权限)
    responses={  # 为此路由器下的所有路由统一定义可能的错误响应
        http_status.HTTP_401_UNAUTHORIZED: {
            "description": "Token缺失或无效 (Unauthorized)"
        },
        http_status.HTTP_403_FORBIDDEN: {
            "description": "权限不足 (非管理员用户) (Forbidden)"
        },
    },
)
# endregion


# region Admin Settings API 端点 (管理员设置接口)
@admin_router.get(
    "/settings",
    response_model=SettingsResponseModel,
    summary="获取当前系统配置",
    description="管理员获取当前应用的主要配置项信息。注意：此接口返回的配置主要反映 `settings.json` 文件的内容，可能不完全包含通过环境变量最终生效的配置值。敏感信息（如数据库密码）不会在此接口返回。",
    responses={
        http_status.HTTP_200_OK: {"description": "成功获取配置信息"},
        # 401/403 are handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "服务器内部错误导致无法获取配置"
        },
    },
)
async def admin_get_settings():
    """
    获取当前应用的配置信息 (主要反映 `settings.json` 的内容)。
    实际生效的配置是合并了环境变量后的内存中 `settings` 对象。
    此接口旨在提供 `settings.json` 的可编辑视图（尽管环境变量优先级更高）。
    """
    _admin_routes_logger.info("管理员请求获取应用配置。")
    # 从 SettingsCRUD 获取文件中的配置
    current_settings_from_file = settings_crud.get_current_settings_from_file()
    try:
        # 转换为响应模型
        return SettingsResponseModel(**current_settings_from_file)
    except Exception as e:
        _admin_routes_logger.error(f"将文件配置转换为SettingsResponseModel时出错: {e}")
        # 在转换失败时返回一个空的或默认的响应模型，避免直接暴露错误细节
        return SettingsResponseModel()  # 或者可以抛出500错误


@admin_router.post(
    "/settings",
    response_model=SettingsResponseModel,
    summary="更新系统配置",
    description="管理员更新应用的部分或全部可配置项。请求体中仅需包含需要修改的字段及其新值。更新操作会写入 `settings.json` 文件并尝试动态重新加载配置到应用内存。注意：通过环境变量设置的配置项具有最高优先级，其在内存中的值不会被此API调用修改，但 `settings.json` 文件中的对应值会被更新。",
    responses={
        http_status.HTTP_200_OK: {
            "description": "配置成功更新并已重新加载，返回更新后的配置状态"
        },
        http_status.HTTP_400_BAD_REQUEST: {
            "description": "提供的配置数据无效或不符合约束"
        },
        http_status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "请求体验证失败 (FastAPI自动处理)"
        },
        # 401/403 are handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "配置文件写入失败或更新时发生未知服务器错误"
        },
    },
)
async def admin_update_settings(
    payload: SettingsUpdatePayload,
):
    """
    更新应用的配置项 (写入 `settings.json` 并重新加载全局配置)。
    注意：.env 文件中的配置项优先级更高，不会被此接口的更新覆盖内存中的实际生效值，
    但 `settings.json` 文件会被更新。部分配置项可能需要重启应用才能完全生效。
    """
    _admin_routes_logger.info(
        f"管理员尝试更新应用配置，数据: {payload.model_dump_json(indent=2)}"
    )
    try:
        # `exclude_unset=True` 确保只传递请求体中实际提供的字段进行更新
        await settings_crud.update_settings_file_and_reload(
            payload.model_dump(exclude_unset=True)
        )
        # 返回更新后从文件（可能被.env部分覆盖后）重新加载的配置的目标状态
        settings_from_file_after_update = settings_crud.get_current_settings_from_file()
        _admin_routes_logger.info("应用配置已成功更新并重新加载。")
        return SettingsResponseModel(**settings_from_file_after_update)
    except ValueError as e_val:  # 通常是Pydantic验证错误或业务逻辑错误
        _admin_routes_logger.warning(f"管理员更新配置失败 (数据验证错误): {e_val}")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(e_val)
        ) from e_val
    except IOError as e_io:  # 文件读写错误
        _admin_routes_logger.error(f"管理员更新配置失败 (文件写入错误): {e_io}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="配置文件写入失败。",
        ) from e_io
    except RuntimeError as e_rt:  # 其他在CRUD层定义的运行时错误
        _admin_routes_logger.error(f"管理员更新配置失败 (运行时错误): {e_rt}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e_rt)
        ) from e_rt
    except Exception as e:  # 未知错误
        _admin_routes_logger.error(f"管理员更新配置时发生未知错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新配置时发生意外错误。",
        ) from e


# endregion


# region Admin User Management API 端点 (管理员用户管理接口)
@admin_router.get(
    "/users",
    response_model=List[UserPublicProfile],
    summary="管理员获取用户列表",
    description="获取系统中的用户账户列表，支持分页查询。返回的用户信息不包含敏感数据（如哈希密码）。",
    responses={
        http_status.HTTP_200_OK: {"description": "成功获取用户列表"},
        # 401/403 handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "获取用户列表时发生服务器内部错误"
        },
    },
)
async def admin_get_all_users(
    skip: int = Query(0, ge=0, description="跳过的记录数，用于分页"),
    limit: int = Query(
        100, ge=1, le=200, description="返回的最大记录数，用于分页 (最大200)"
    ),
):
    """
    管理员获取系统中的所有用户列表（分页）。
    返回的用户信息是公开的个人资料，不包含敏感数据如哈希密码。
    参数:
        skip (int): 跳过的记录数，用于分页。
        limit (int): 返回的最大记录数，用于分页。
    """
    _admin_routes_logger.info(f"管理员请求用户列表，skip={skip}, limit={limit}。")
    users_in_db = await user_crud.admin_get_all_users(skip=skip, limit=limit)
    # 将数据库模型转换为公开的Pydantic模型列表
    return [UserPublicProfile.model_validate(user) for user in users_in_db]


@admin_router.get(
    "/users/{user_uid}",
    response_model=UserPublicProfile,
    summary="管理员获取特定用户信息",
    description="根据用户UID（用户名）获取其公开的详细信息，不包括密码等敏感内容。",
    responses={
        http_status.HTTP_200_OK: {"description": "成功获取用户信息"},
        http_status.HTTP_404_NOT_FOUND: {"description": "指定UID的用户未找到"},
        # 401/403 handled by router dependency
    },
)
async def admin_get_user(
    *, user_uid: str = Path(..., description="要获取详情的用户的UID")
):
    """管理员获取指定UID用户的详细信息。"""
    _admin_routes_logger.info(f"管理员请求用户 '{user_uid}' 的详细信息。")
    user = await user_crud.get_user_by_uid(user_uid)
    if not user:  # 如果用户未找到
        _admin_routes_logger.warning(f"管理员请求用户 '{user_uid}' 失败：用户未找到。")
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="用户未找到"
        )
    return UserPublicProfile.model_validate(user)


@admin_router.put(
    "/users/{user_uid}",
    response_model=UserPublicProfile,
    summary="管理员更新特定用户信息",
    description="管理员修改用户的昵称、邮箱、QQ、用户标签，或为其重置密码。请求体中仅需包含需要修改的字段。",
    responses={
        http_status.HTTP_200_OK: {"description": "用户信息成功更新"},
        http_status.HTTP_400_BAD_REQUEST: {
            "description": "提供的更新数据无效（例如，无效的标签值）"
        },
        http_status.HTTP_404_NOT_FOUND: {"description": "指定UID的用户未找到"},
        http_status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "请求体验证失败"},
        # 401/403 handled by router dependency
    },
)
async def admin_update_user_info(
    *,
    user_uid: str = Path(..., description="要更新信息的用户的UID"),
    update_payload: AdminUserUpdate,
):
    """
    管理员更新指定UID用户的信息，包括昵称、邮箱、QQ、标签和可选的密码重置。
    """
    _admin_routes_logger.info(
        f"管理员尝试更新用户 '{user_uid}' 的信息，数据: {update_payload.model_dump_json(exclude_none=True)}"
    )
    updated_user = await user_crud.admin_update_user(user_uid, update_payload)
    if not updated_user:
        # 失败原因可能包括用户不存在或更新数据验证失败，具体已在CRUD层记录日志
        _admin_routes_logger.warning(
            f"管理员更新用户 '{user_uid}' 失败：用户未找到或更新无效。"
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,  # 或400，取决于具体失败原因
            detail="用户未找到或更新失败。",
        )
    _admin_routes_logger.info(f"管理员成功更新用户 '{user_uid}' 的信息。")
    # 注意：如果管理员更新了用户密码，理想情况下可能需要使用户所有现有Token失效，
    # 这需要更复杂的Token管理机制（例如，Token黑名单或版本控制）。当前实现较为简单。
    return UserPublicProfile.model_validate(updated_user)


# endregion


# region Admin Paper Management API 端点 (管理员试卷管理接口)
@admin_router.get(
    "/papers",  # RESTful: 使用复数名词 (papers)
    response_model=List[PaperAdminView],
    summary="管理员获取所有试卷摘要列表",
    description="获取系统生成的所有试卷的摘要信息列表，支持分页。摘要信息包括试卷ID、用户UID、创建时间、题目数、得分等。",
    responses={
        http_status.HTTP_200_OK: {"description": "成功获取试卷摘要列表"},
        # 401/403 handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "获取试卷列表时发生服务器内部错误"
        },
    },
)
async def admin_get_all_papers_summary(
    skip: int = Query(0, ge=0, description="跳过的记录数，用于分页"),
    limit: int = Query(100, ge=1, le=200, description="返回的最大记录数 (最大200)"),
):
    """获取存储中所有试卷的摘要信息列表，按创建时间倒序排列。"""
    _admin_routes_logger.info(f"管理员请求试卷摘要列表，skip={skip}, limit={limit}。")
    try:
        # 从PaperCRUD获取试卷摘要数据
        all_papers_data = await paper_crud.admin_get_all_papers_summary(skip, limit)
        # PaperAdminView 模型应该能直接从 paper_crud 返回的数据进行实例化
        return [PaperAdminView(**paper_data) for paper_data in all_papers_data]
    except Exception as e:
        _admin_routes_logger.error(
            f"管理员获取试卷列表时发生意外错误: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取试卷列表时发生错误: {str(e)}",
        ) from e


@admin_router.get(
    "/papers/{paper_id}",  # RESTful: 使用路径参数
    response_model=PaperFullDetailModel,
    summary="管理员获取特定试卷的完整信息",
    description="根据试卷ID获取其完整详细信息，包括所有题目、正确答案映射、用户作答情况等。",
    responses={
        http_status.HTTP_200_OK: {"description": "成功获取试卷详细信息"},
        http_status.HTTP_404_NOT_FOUND: {"description": "指定ID的试卷未找到"},
        # 401/403 handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "获取试卷详情时发生服务器内部错误"
        },
    },
)
async def admin_get_paper_detail(
    paper_id: str = Path(
        ..., description="要获取详情的试卷ID (UUID格式)"
    )  # 改为路径参数
):
    """获取指定 `paper_id` 的试卷的完整详细信息。"""
    _admin_routes_logger.info(f"管理员请求试卷 '{paper_id}' 的详细信息。")
    paper_data = await paper_crud.admin_get_paper_detail(paper_id)
    if not paper_data:
        _admin_routes_logger.warning(f"管理员请求试卷 '{paper_id}' 失败：试卷未找到。")
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"试卷ID '{paper_id}' 未找到。",
        )
    try:
        # 确保 paper_questions 字段存在且为列表，以防数据损坏或不一致
        if "paper_questions" not in paper_data or not isinstance(
            paper_data["paper_questions"], list
        ):
            paper_data["paper_questions"] = []  # 如果缺失，则设置为空列表
        return PaperFullDetailModel(**paper_data)  # 转换为响应模型
    except Exception as e:  # 通常是 Pydantic ValidationError
        _admin_routes_logger.error(
            f"管理员获取试卷 '{paper_id}' 详情时，转换数据模型失败: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"试卷数据格式错误或不完整: {str(e)}",
        ) from e


@admin_router.delete(
    "/papers/{paper_id}",  # RESTful: 使用路径参数
    status_code=http_status.HTTP_204_NO_CONTENT,  # 成功删除通常返回 204
    summary="管理员删除特定试卷",
    description="根据试卷ID永久删除一份试卷及其所有相关数据。此操作需谨慎，成功时无内容返回。",
    responses={
        http_status.HTTP_204_NO_CONTENT: {"description": "试卷成功删除"},
        http_status.HTTP_404_NOT_FOUND: {"description": "指定ID的试卷未找到"},
        # 401/403 handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "删除试卷时发生服务器内部错误"
        },
    },
)
async def admin_delete_paper(
    paper_id: str = Path(..., description="要删除的试卷ID (UUID格式)")  # 改为路径参数
):
    """从数据存储中删除指定 `paper_id` 的试卷记录。"""
    _admin_routes_logger.info(f"管理员尝试删除试卷 '{paper_id}'。")
    deleted = await paper_crud.admin_delete_paper(paper_id)
    if not deleted:
        _admin_routes_logger.warning(f"管理员删除试卷 '{paper_id}' 失败：试卷未找到。")
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"试卷ID '{paper_id}' 未找到，无法删除。",
        )
    _admin_routes_logger.info(f"管理员已成功删除试卷: {paper_id}。")
    return None  # 对于 204 No Content，不应返回任何内容


# endregion


# region Admin Question Bank Management API 端点 (管理员题库管理接口)


@admin_router.get(
    "/question-banks",
    response_model=List[LibraryIndexItem],
    summary="管理员获取所有题库的元数据列表",
    description="获取系统中所有题库的元数据信息列表，包括ID、名称、描述、题目总数等。这与公共的 `/difficulties` 接口类似，但处于管理员路径下。",
    responses={
        http_status.HTTP_200_OK: {"description": "成功获取题库元数据列表"},
        # 401/403 handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "获取题库元数据时发生服务器内部错误"
        },
    },
)
async def admin_get_all_qbank_metadata():
    """管理员获取所有题库的元数据列表。"""
    _admin_routes_logger.info("管理员请求获取所有题库的元数据。")
    try:
        metadata_list = await qb_crud.get_all_library_metadatas()
        return metadata_list
    except Exception as e:
        _admin_routes_logger.error(
            f"管理员获取题库元数据列表时发生错误: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取题库元数据列表时发生错误: {str(e)}",
        )


@admin_router.get(
    "/question-banks/{difficulty_id}/content",
    response_model=QuestionBank,  # 返回包含元数据和题目列表的完整题库模型
    summary="管理员获取特定难度题库的完整内容",
    description="根据难度ID（例如 'easy', 'hard'）获取指定题库的元数据及其包含的所有题目详情。",
    responses={
        http_status.HTTP_200_OK: {"description": "成功获取题库内容"},
        http_status.HTTP_404_NOT_FOUND: {"description": "指定难度的题库未找到"},
        # 401/403 handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "获取题库内容时发生服务器内部错误"
        },
    },
)
async def admin_get_question_bank_content(  # 函数名修改以反映其行为
    difficulty_id: DifficultyLevel = Path(
        ..., description="要获取内容的题库难度ID (例如: easy, hybrid, hard)"
    )
):
    """获取指定难度题库的元数据和所有题目。"""
    _admin_routes_logger.info(
        f"管理员请求获取难度为 '{difficulty_id.value}' 的题库内容。"
    )
    try:
        full_bank = await qb_crud.get_question_bank_with_content(difficulty_id)
        if not full_bank:
            _admin_routes_logger.warning(
                f"管理员请求难度 '{difficulty_id.value}' 的题库内容失败：题库未找到或为空。"
            )
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"难度为 '{difficulty_id.value}' 的题库未加载或不存在。",
            )
        return full_bank  # 直接返回 QuestionBank 对象
    except HTTPException:
        raise
    except Exception as e:
        _admin_routes_logger.error(
            f"管理员获取题库 '{difficulty_id.value}' 内容时发生意外错误: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取题库 '{difficulty_id.value}' 内容时发生服务器错误。",
        ) from e


@admin_router.post(
    "/question-banks/{difficulty_id}/questions",
    response_model=QuestionModel,
    status_code=http_status.HTTP_201_CREATED,
    summary="管理员向特定题库添加新题目",
    description="向指定难度的题库中添加一道新的题目。请求体应为单个题目的完整数据结构。",
    responses={
        http_status.HTTP_201_CREATED: {"description": "题目成功添加到题库"},
        http_status.HTTP_400_BAD_REQUEST: {
            "description": "提供的题目数据无效或不符合约束"
        },
        http_status.HTTP_404_NOT_FOUND: {"description": "指定难度的题库未找到"},
        http_status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "请求体验证失败"},
        # 401/403 handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "添加题目到题库时发生服务器内部错误"
        },
    },
)
async def admin_add_question_to_bank(
    question: QuestionModel,  # 请求体包含新题目数据
    difficulty_id: DifficultyLevel = Path(..., description="要添加题目的题库难度ID"),
):
    """向指定难度的题库添加一个新题目。"""
    _admin_routes_logger.info(
        f"管理员尝试向题库 '{difficulty_id.value}' 添加新题目: {question.body[:50]}..."
    )
    try:
        added_question = await qb_crud.add_question_to_bank(difficulty_id, question)
        if not added_question:
            _admin_routes_logger.error(
                f"管理员向题库 '{difficulty_id.value}' 添加题目失败（CRUD层返回None）。"
            )
            # CRUD层应在失败时抛出异常，如果返回None则表示一种未预期的成功指示失败
            raise HTTPException(
                status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="添加题目到题库失败，但CRUD未明确报告错误原因。",
            )
        _admin_routes_logger.info(
            f"管理员已成功向题库 '{difficulty_id.value}' 添加新题目。"
        )
        return added_question
    except ValueError as ve:  # 例如，如果CRUD层在找不到元数据时抛出ValueError
        _admin_routes_logger.warning(
            f"向题库 '{difficulty_id.value}' 添加题目失败: {ve}"
        )
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        _admin_routes_logger.error(
            f"向题库 '{difficulty_id.value}' 添加题目时发生意外错误: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"向题库 '{difficulty_id.value}' 添加题目时发生服务器错误。",
        )


@admin_router.delete(
    "/question-banks/{difficulty_id}/questions",
    status_code=http_status.HTTP_204_NO_CONTENT,  # 成功删除通常返回204 No Content
    summary="管理员从特定题库删除题目",
    description="根据题目在题库列表中的索引，从指定难度的题库中删除一道题目。成功时无内容返回。",
    responses={
        http_status.HTTP_204_NO_CONTENT: {"description": "题目成功删除"},
        http_status.HTTP_400_BAD_REQUEST: {"description": "提供的索引无效"},
        http_status.HTTP_404_NOT_FOUND: {
            "description": "指定难度的题库或指定索引的题目未找到"
        },
        # 401/403 handled by router dependency
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "删除题目时发生服务器内部错误"
        },
    },
)
async def admin_delete_question_from_bank(
    difficulty_id: DifficultyLevel = Path(..., description="要删除题目的题库难度ID"),
    question_index: int = Query(
        ..., alias="index", ge=0, description="要删除的题目在列表中的索引 (从0开始)"
    ),
):
    """根据索引从指定难度的题库中删除一个题目。"""
    _admin_routes_logger.info(
        f"管理员尝试从题库 '{difficulty_id.value}' 删除索引为 {question_index} 的题目。"
    )
    try:
        deleted_question_data = await qb_crud.delete_question_from_bank(
            difficulty_id, question_index
        )
        if deleted_question_data is None:
            _admin_routes_logger.warning(
                f"管理员删除题库 '{difficulty_id.value}' 索引 {question_index} 的题目失败（可能索引无效或题目不存在）。"
            )
            # 根据CRUD返回None的具体原因，可能404更合适
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,  # 假设索引不存在或题库不存在
                detail=f"在题库 '{difficulty_id.value}' 中未找到索引为 {question_index} 的题目，或题库本身不存在。",
            )
        deleted_body = deleted_question_data.get("body", "N/A")
        _admin_routes_logger.info(
            f"管理员已成功从题库 '{difficulty_id.value}' 删除索引为 {question_index} 的题目: {deleted_body[:50]}..."
        )
        return None  # 对于 204 No Content，不应返回任何内容
    except ValueError as ve:  # CRUD层可能因无法找到元数据而抛出ValueError
        _admin_routes_logger.warning(
            f"从题库 '{difficulty_id.value}' 删除题目失败: {ve}"
        )
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        _admin_routes_logger.error(
            f"从题库 '{difficulty_id.value}' 删除题目时发生意外错误: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"从题库 '{difficulty_id.value}' 删除题目时发生服务器错误。",
        )


# endregion

__all__ = ["admin_router"]  # 导出管理员路由实例，供 app.main 挂载

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义API路由，应由FastAPI应用实例导入和使用。
    _admin_routes_logger.info(
        f"模块 {__name__} 定义了管理员相关的API路由，不应直接执行。它应被 FastAPI 应用导入。"
    )
    print(
        f"模块 {__name__} 定义了管理员相关的API路由，不应直接执行。它应被 FastAPI 应用导入。"
    )
