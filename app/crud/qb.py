# -*- coding: utf-8 -*-
"""
题库数据管理模块 (Question Bank Data Management Module)。

此模块定义了 `QuestionBankCRUD` 类，用于处理所有与题库相关的创建、读取、更新和删除 (CRUD) 操作。
它通过依赖注入的 `IDataStorageRepository` 与底层数据存储进行交互，管理题库的元数据和题目内容。
主要功能包括加载题库索引、获取特定难度的题库（元数据和题目列表）、以及对题库内容（题目）的增删操作。

(This module defines the `QuestionBankCRUD` class for handling all Create, Read, Update, and Delete (CRUD)
operations related to question banks. It interacts with the underlying data storage through a
dependency-injected `IDataStorageRepository`, managing both metadata and content of question banks.
Key functionalities include loading the library index, fetching question banks of specific difficulties
(metadata and question lists), and adding/deleting questions within a bank.)
"""

# region 模块导入 (Module Imports)
import logging
from typing import Any, Dict, List, Optional

from ..core.config import (
    DifficultyLevel,
)  # 导入全局配置和难度枚举 (Import global config and DifficultyLevel enum)
from ..core.interfaces import (
    IDataStorageRepository,
)  # 数据存储库接口 (Data storage repository interface)
from ..models.qb_models import (
    LibraryIndexItem,
    QuestionBank,
    QuestionModel,
)  # 题库相关的Pydantic模型 (QB-related Pydantic models)

# endregion

# region 全局变量与初始化 (Global Variables & Initialization)
_qb_crud_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例
QB_METADATA_ENTITY_TYPE = "question_bank_metadata"  # 题库元数据实体的类型字符串
QB_CONTENT_ENTITY_TYPE_PREFIX = (
    "qb_content_"  # 题库内容实体的类型字符串前缀 (用于区分不同难度的内容)
)
# endregion


# region 题库管理类 (QuestionBankCRUD)
class QuestionBankCRUD:
    """
    题库管理类 (QuestionBankCRUD)。
    通过 IDataStorageRepository 与底层数据存储交互。
    (Question Bank Management Class (QuestionBankCRUD).
    Interacts with the underlying data storage via IDataStorageRepository.)
    """

    def __init__(self, repository: IDataStorageRepository):
        """
        初始化 QuestionBankCRUD。
        (Initializes QuestionBankCRUD.)

        参数 (Args):
            repository (IDataStorageRepository): 实现 IDataStorageRepository 接口的存储库实例。
                                                 (Instance of a repository implementing IDataStorageRepository.)
        """
        self.repository = repository
        _qb_crud_logger.info(
            "QuestionBankCRUD 已初始化并注入存储库。 (QuestionBankCRUD initialized with injected repository.)"
        )

    async def initialize_storage(self) -> None:
        """
        确保题库元数据和内容的存储已初始化（如果需要）。应在应用启动时调用一次。
        (Ensures that the storage for question bank metadata and content is initialized if needed.
        Should be called once during application startup.)
        """
        # 初始化元数据存储 (Initialize metadata storage)
        await self.repository.init_storage_if_needed(
            QB_METADATA_ENTITY_TYPE, initial_data=[]
        )
        _qb_crud_logger.info(
            f"实体类型 '{QB_METADATA_ENTITY_TYPE}' 的存储已初始化（如果需要）。 (Storage for entity type '{QB_METADATA_ENTITY_TYPE}' initialized if needed.)"
        )

        # 题库内容文件的初始化可以根据需要在此处添加，或者由首次访问时动态创建。
        # (Initialization for question bank content files can be added here if needed,
        #  or they can be dynamically created upon first access.)
        # 例如，如果知道所有难度级别，可以预先为每个难度创建内容实体：
        # (For example, if all difficulty levels are known, content entities can be pre-created:)
        # for difficulty in DifficultyLevel:
        #     content_entity_type = f"{QB_CONTENT_ENTITY_TYPE_PREFIX}{difficulty.value}"
        #     await self.repository.init_storage_if_needed(content_entity_type, initial_data={"id": difficulty.value, "questions": []})
        # _qb_crud_logger.info("所有已知难度题库内容的存储已检查/创建。 (Storage for all known difficulty QB contents checked/created.)")

    async def _read_library_index_internal(self) -> List[Dict[str, Any]]:
        """
        从存储库读取所有题库元数据项。
        (Reads all question bank metadata items from the repository.)
        """
        metadata_list = await self.repository.get_all(
            QB_METADATA_ENTITY_TYPE, limit=1000
        )  # 假设最多1000个难度级别 (Assuming max 1000 difficulties)
        return metadata_list

    async def get_all_library_metadatas(self) -> List[LibraryIndexItem]:
        """
        获取所有题库的元数据列表 (从 repository 读取并验证)。
        (Gets the list of all question bank metadata (read from repository and validated).)
        """
        _qb_crud_logger.debug(
            "正在获取所有题库元数据... (Fetching all question bank metadata...)"
        )
        index_data_dicts = await self._read_library_index_internal()
        valid_metadatas: List[LibraryIndexItem] = []
        for item_dict in index_data_dicts:
            try:
                lib_item = LibraryIndexItem(
                    **item_dict
                )  # 使用Pydantic模型进行验证和转换
                valid_metadatas.append(lib_item)
            except Exception as e_val:  # Pydantic ValidationError
                _qb_crud_logger.warning(
                    f"题库索引中发现无效元数据项 (Invalid metadata item found in library index): {item_dict}, 错误 (Error): {e_val}"
                )
        _qb_crud_logger.info(
            f"成功加载 {len(valid_metadatas)} 个有效的题库元数据项。 (Successfully loaded {len(valid_metadatas)} valid QB metadata items.)"
        )
        return valid_metadatas

    async def get_library_metadata_by_id(
        self, difficulty_id: str
    ) -> Optional[LibraryIndexItem]:
        """
        根据难度ID (字符串) 获取单个题库的元数据。
        (Gets metadata for a single question bank by difficulty ID (string).)
        """
        # 直接从存储库获取，而不是先获取全部再过滤 (Fetch directly from repository instead of getting all then filtering)
        metadata_dict = await self.repository.get_by_id(
            QB_METADATA_ENTITY_TYPE, difficulty_id
        )
        if metadata_dict:
            try:
                return LibraryIndexItem(**metadata_dict)
            except Exception as e_val:
                _qb_crud_logger.warning(
                    f"题库元数据 (ID: {difficulty_id}) 无效 (Invalid metadata for QB (ID: {difficulty_id})): {metadata_dict}, 错误 (Error): {e_val}"
                )
                return None
        return None

    async def _read_question_bank_file_content_internal(
        self, difficulty_id: str
    ) -> List[Dict[str, Any]]:
        """
        从存储库为指定难度读取题库内容（题目列表）。
        (Reads question bank content (list of questions) for a specific difficulty from the repository.)
        """
        entity_type = f"{QB_CONTENT_ENTITY_TYPE_PREFIX}{difficulty_id}"
        # 题库内容实体ID约定为 difficulty_id (QB content entity ID convention is difficulty_id)
        content_doc = await self.repository.get_by_id(entity_type, difficulty_id)
        if (
            content_doc
            and "questions" in content_doc
            and isinstance(content_doc["questions"], list)
        ):
            return content_doc["questions"]
        _qb_crud_logger.warning(
            f"未找到题库 '{difficulty_id}' 的内容或内容格式错误。 (No content found or content format error for question bank '{difficulty_id}'.)"
        )
        return []

    async def _write_question_bank_file_content_internal(
        self, difficulty_id: str, questions_data: List[Dict[str, Any]]
    ) -> bool:
        """
        将指定难度的题库内容（题目列表）写入存储库。
        (Writes question bank content (list of questions) for a specific difficulty to the repository.)
        """
        entity_type = f"{QB_CONTENT_ENTITY_TYPE_PREFIX}{difficulty_id}"
        # 整个题目列表作为单个文档中的一个字段存储 (Entire list of questions stored as a field in a single document)
        # 文档ID约定为 difficulty_id (Document ID convention is difficulty_id)
        content_doc = {
            "id": difficulty_id,
            "questions": questions_data,
        }  # 确保文档本身有 'id' 字段

        existing_doc = await self.repository.get_by_id(entity_type, difficulty_id)
        if existing_doc:  # 如果已存在，则更新 (If exists, update)
            updated_doc = await self.repository.update(
                entity_type, difficulty_id, content_doc
            )
            return updated_doc is not None
        else:  # 否则，创建新文档 (Otherwise, create new document)
            created_doc = await self.repository.create(entity_type, content_doc)
            return created_doc is not None

    async def get_question_bank_with_content(
        self, difficulty: DifficultyLevel
    ) -> Optional[QuestionBank]:
        """
        获取指定难度的完整题库（元数据+题目内容），并用Pydantic模型验证。
        (Gets the complete question bank for a specified difficulty (metadata + content),
         validated with Pydantic models.)
        """
        _qb_crud_logger.debug(
            f"正在获取难度为 '{difficulty.value}' 的完整题库... (Fetching full question bank for difficulty '{difficulty.value}'...)"
        )
        meta = await self.get_library_metadata_by_id(difficulty.value)
        if not meta:
            _qb_crud_logger.warning(
                f"未找到难度 '{difficulty.value}' 的题库元数据。 (Metadata not found for difficulty '{difficulty.value}'.)"
            )
            return None

        content_dicts = await self._read_question_bank_file_content_internal(
            difficulty.value
        )
        questions_models: List[QuestionModel] = []
        for q_idx, q_dict in enumerate(content_dicts):  # 为题目添加索引日志
            try:
                questions_models.append(QuestionModel(**q_dict))
            except Exception as e_val:
                _qb_crud_logger.warning(
                    f"题库 '{difficulty.value}' 中题目索引 {q_idx} 数据验证失败 (Question data validation failed for index {q_idx} in bank '{difficulty.value}'): {str(q_dict)[:100]}..., 错误 (Error): {e_val}"
                )

        # 验证元数据中的题目总数与实际加载的题目数是否一致 (Validate total_questions in metadata against actual loaded count)
        if meta.total_questions != len(questions_models):
            _qb_crud_logger.warning(
                f"题库 '{meta.id}' 元数据中的 total_questions ({meta.total_questions}) "
                f"与实际加载的有效题目数量 ({len(questions_models)}) 不符。将使用实际加载数量更新元数据。"
                f"(total_questions ({meta.total_questions}) in metadata for bank '{meta.id}' "
                f"does not match actual loaded valid questions count ({len(questions_models)}). "
                f"Metadata will be updated with actual loaded count.)"
            )
            meta.total_questions = len(questions_models)
            await self.repository.update(
                QB_METADATA_ENTITY_TYPE, meta.id, meta.model_dump()
            )  # 更新存储库中的元数据

        return QuestionBank(metadata=meta, questions=questions_models)

    async def add_question_to_bank(
        self, difficulty: DifficultyLevel, question_model_data: QuestionModel
    ) -> Optional[QuestionModel]:
        """
        向指定难度的题库添加一个新题目，并更新元数据中的题目总数。
        (Adds a new question to the question bank of specified difficulty and updates total_questions in metadata.)
        """
        difficulty_id = difficulty.value
        _qb_crud_logger.info(
            f"向题库 '{difficulty_id}' 添加新题目... (Adding new question to bank '{difficulty_id}'...)"
        )
        current_questions_list = await self._read_question_bank_file_content_internal(
            difficulty_id
        )
        current_questions_list.append(
            question_model_data.model_dump()
        )  # 添加新题目数据

        if await self._write_question_bank_file_content_internal(
            difficulty_id, current_questions_list
        ):
            meta = await self.get_library_metadata_by_id(
                difficulty_id
            )  # 获取元数据以更新总数
            if meta:
                meta.total_questions = len(current_questions_list)
                await self.repository.update(
                    QB_METADATA_ENTITY_TYPE, difficulty_id, meta.model_dump()
                )
                _qb_crud_logger.info(
                    f"题库 '{difficulty_id}' 元数据已更新，新总题目数: {meta.total_questions}。 (Metadata for bank '{difficulty_id}' updated, new total questions: {meta.total_questions}.)"
                )
            else:  # 如果元数据不存在，这通常不应该发生，除非索引文件损坏或未正确初始化
                _qb_crud_logger.error(
                    f"未找到题库 '{difficulty_id}' 的元数据，无法更新题目总数！ (Metadata for bank '{difficulty_id}' not found, cannot update total questions!)"
                )
            _qb_crud_logger.info(
                f"题目已成功添加到题库 '{difficulty_id}'。 (Question successfully added to bank '{difficulty_id}'.)"
            )
            return question_model_data
        _qb_crud_logger.error(
            f"向题库 '{difficulty_id}' 添加题目失败（写入存储失败）。 (Failed to add question to bank '{difficulty_id}' (write to storage failed).)"
        )
        return None

    async def delete_question_from_bank(
        self, difficulty: DifficultyLevel, question_index: int
    ) -> Optional[Dict[str, Any]]:
        """
        从指定难度的题库中按索引删除一个题目，并更新元数据中的题目总数。
        (Deletes a question by index from the question bank of specified difficulty and updates total_questions in metadata.)
        """
        difficulty_id = difficulty.value
        _qb_crud_logger.info(
            f"从题库 '{difficulty_id}' 删除索引为 {question_index} 的题目... (Deleting question at index {question_index} from bank '{difficulty_id}'...)"
        )
        current_questions_list = await self._read_question_bank_file_content_internal(
            difficulty_id
        )

        if not (0 <= question_index < len(current_questions_list)):  # 检查索引有效性
            _qb_crud_logger.warning(
                f"尝试从题库 '{difficulty_id}' 删除无效的索引: {question_index}。 (Attempted to delete invalid index {question_index} from bank '{difficulty_id}'.)"
            )
            return None

        deleted_question_dict = current_questions_list.pop(question_index)  # 移除题目

        if await self._write_question_bank_file_content_internal(
            difficulty_id, current_questions_list
        ):
            meta = await self.get_library_metadata_by_id(difficulty_id)  # 更新元数据
            if meta:
                meta.total_questions = len(current_questions_list)
                await self.repository.update(
                    QB_METADATA_ENTITY_TYPE, difficulty_id, meta.model_dump()
                )
                _qb_crud_logger.info(
                    f"题库 '{difficulty_id}' 元数据已更新，新总题目数: {meta.total_questions}。 (Metadata for bank '{difficulty_id}' updated, new total questions: {meta.total_questions}.)"
                )
            else:
                _qb_crud_logger.error(
                    f"未找到题库 '{difficulty_id}' 的元数据，无法更新题目总数！ (Metadata for bank '{difficulty_id}' not found, cannot update total questions!)"
                )
            _qb_crud_logger.info(
                f"已从题库 '{difficulty_id}' 成功删除索引为 {question_index} 的题目。 (Successfully deleted question at index {question_index} from bank '{difficulty_id}'.)"
            )
            return deleted_question_dict  # 返回被删除的题目数据
        _qb_crud_logger.error(
            f"从题库 '{difficulty_id}' 删除题目失败（写入存储失败）。 (Failed to delete question from bank '{difficulty_id}' (write to storage failed).)"
        )
        return None


# endregion

__all__ = [
    "QuestionBankCRUD",  # 导出QuestionBankCRUD类
    "QB_METADATA_ENTITY_TYPE",  # 导出元数据实体类型常量
    "QB_CONTENT_ENTITY_TYPE_PREFIX",  # 导出内容实体类型前缀常量
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了题库数据的CRUD操作类。
    # (This module should not be executed as the main script. It defines the CRUD operations class for question bank data.)
    _qb_crud_logger.info(f"模块 {__name__} 提供了题库数据的CRUD操作类，不应直接执行。")
    print(
        f"模块 {__name__} 提供了题库数据的CRUD操作类，不应直接执行。 (This module provides CRUD operations class for question bank data and should not be executed directly.)"
    )
