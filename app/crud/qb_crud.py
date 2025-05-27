# -*- coding: utf-8 -*-
# region 模块导入
import json
import os
import asyncio
import copy # 用于深拷贝
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

# 使用相对导入
from .models.qb_models import QuestionModel, LibraryIndexItem, QuestionBank
from .core.config import settings, DifficultyLevel # 导入全局配置和难度枚举
# 注意：不直接从这里导入 paper_crud 来避免循环依赖。
# 题库内容更新后，重新加载 paper_crud 内存中题库的逻辑应由调用方（如admin_routes）协调。
# endregion

# region 全局变量与初始化
_qb_crud_logger = logging.getLogger(__name__)
_library_index_lock = asyncio.Lock() # 用于同步访问 library/index.json
_question_file_locks: Dict[str, asyncio.Lock] = {} # 用于同步访问各个题库文件, key为difficulty_id(str)
# endregion

# region 题库管理类 (QuestionBankCRUD)
class QuestionBankCRUD:
    """
    题库管理类 (QuestionBankCRUD)。
    负责管理题库元数据 (library/index.json) 和各个题库文件的内容。
    所有文件操作都是异步和加锁的，以保证数据一致性。
    """

    def __init__(self):
        """初始化 QuestionBankCRUD。"""
        self.library_path: Path = settings.get_library_path()
        self.index_file_path: Path = settings.get_library_index_path()
        
        # 确保题库目录和索引文件在初始化时存在 (config.py中已处理了首次创建)
        # 此处可以再次检查，以防万一
        self.library_path.mkdir(parents=True, exist_ok=True)
        if not self.index_file_path.exists():
            try:
                with open(self.index_file_path, "w", encoding="utf-8") as f:
                    json.dump([], f) # 初始化为空列表
                _qb_crud_logger.info(f"已创建空的题库索引文件: '{self.index_file_path}'")
            except IOError as e:
                _qb_crud_logger.error(f"无法创建题库索引文件 '{self.index_file_path}': {e}")
                # 这是一个严重问题，后续操作可能失败

    async def _read_library_index_internal(self) -> List[Dict[str, Any]]:
        """[内部方法] 异步安全地读取题库索引文件内容。"""
        async with _library_index_lock:
            if not self.index_file_path.exists():
                _qb_crud_logger.warning(f"题库索引文件 '{self.index_file_path}' 不存在，返回空列表。")
                return []
            try:
                with open(self.index_file_path, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
                if not isinstance(index_data, list):
                    _qb_crud_logger.error(
                        f"题库索引文件 '{self.index_file_path}' 内容格式不正确（不是列表）。"
                        "将视为空索引。"
                    )
                    return [] 
                return index_data
            except (json.JSONDecodeError, IOError) as e:
                _qb_crud_logger.error(f"读取题库索引 '{self.index_file_path}' 失败: {e}")
                return [] # 发生错误时返回空列表，上层应处理此情况

    async def _write_library_index_internal(self, index_data: List[Dict[str, Any]]) -> bool:
        """[内部方法] 异步安全地将题库索引数据写入文件。"""
        async with _library_index_lock:
            try:
                # 确保父目录存在
                self.index_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.index_file_path, "w", encoding="utf-8") as f:
                    json.dump(index_data, f, indent=4, ensure_ascii=False)
                _qb_crud_logger.info(f"题库索引已更新并写入 '{self.index_file_path}'。")
                return True
            except IOError as e:
                _qb_crud_logger.error(f"写入题库索引 '{self.index_file_path}' 失败: {e}")
                return False

    async def get_all_library_metadatas(self) -> List[LibraryIndexItem]:
        """获取所有题库的元数据列表 (从 index.json 读取并验证)。"""
        index_data_dicts = await self._read_library_index_internal()
        valid_metadatas: List[LibraryIndexItem] = []
        for item_dict in index_data_dicts:
            try:
                lib_item = LibraryIndexItem(**item_dict)
                # 确保 total_questions 与实际文件内容一致（可选，但推荐）
                # content = await self._read_question_bank_file_content_internal(lib_item.id)
                # lib_item.total_questions = len(content) # 如果需要实时更新
                valid_metadatas.append(lib_item)
            except Exception as e_val: # Pydantic ValidationError
                _qb_crud_logger.warning(
                    f"题库索引中发现无效元数据项: {item_dict}, 错误: {e_val}"
                )
        return valid_metadatas

    async def get_library_metadata_by_id(self, difficulty_id: str) -> Optional[LibraryIndexItem]:
        """根据难度ID (字符串) 获取单个题库的元数据。"""
        metadatas = await self.get_all_library_metadatas()
        for meta in metadatas:
            if meta.id == difficulty_id:
                return meta
        return None

    async def _get_question_file_lock(self, difficulty_id: str) -> asyncio.Lock:
        """获取或创建特定题库内容文件的异步锁。"""
        # 确保 _question_file_locks 是类级别的或正确初始化的实例变量
        if difficulty_id not in _question_file_locks:
            _question_file_locks[difficulty_id] = asyncio.Lock()
        return _question_file_locks[difficulty_id]

    async def _read_question_bank_file_content_internal(self, difficulty_id: str) -> List[Dict[str, Any]]:
        """[内部方法] 异步安全地读取指定题库文件的内容。"""
        file_path = self.library_path / f"{difficulty_id}.json"
        file_lock = await self._get_question_file_lock(difficulty_id)
        async with file_lock:
            if not file_path.exists():
                _qb_crud_logger.warning(f"题库内容文件 '{file_path}' 不存在，返回空列表。")
                return []
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    questions_raw = json.load(f)
                if not isinstance(questions_raw, list):
                    _qb_crud_logger.error(
                        f"题库文件 '{file_path}' 内容格式不正确（不是列表）。将视为空题库。"
                    )
                    return []
                # 可选：在这里对每条题目进行QuestionModel验证，确保数据质量
                # validated_questions = []
                # for q_raw in questions_raw:
                #     try:
                #         QuestionModel(**q_raw)
                #         validated_questions.append(q_raw)
                #     except Exception: pass # 跳过无效题目
                # return validated_questions
                return questions_raw
            except (json.JSONDecodeError, IOError) as e:
                _qb_crud_logger.error(f"读取题库文件 '{file_path}' 失败: {e}")
                return []

    async def _write_question_bank_file_content_internal(
        self,
        difficulty_id: str,
        questions_data: List[Dict[str, Any]] # 期望是已经 model_dump() 过的字典列表
    ) -> bool:
        """[内部方法] 异步安全地将题目数据写入指定的题库文件。"""
        file_path = self.library_path / f"{difficulty_id}.json"
        file_lock = await self._get_question_file_lock(difficulty_id)
        async with file_lock:
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True) # 确保目录存在
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(questions_data, f, indent=4, ensure_ascii=False)
                _qb_crud_logger.info(f"题库内容已更新并写入 '{file_path}'。")
                return True
            except IOError as e:
                _qb_crud_logger.error(f"写入题库文件 '{file_path}' 失败: {e}")
                return False

    async def get_question_bank_with_content(self, difficulty: DifficultyLevel) -> Optional[QuestionBank]:
        """获取指定难度的完整题库（元数据+题目内容），并用Pydantic模型验证。"""
        meta = await self.get_library_metadata_by_id(difficulty.value)
        if not meta:
            _qb_crud_logger.warning(f"未找到难度 '{difficulty.value}' 的题库元数据。")
            return None
        
        content_dicts = await self._read_question_bank_file_content_internal(difficulty.value)
        questions_models: List[QuestionModel] = []
        for q_dict in content_dicts:
            try:
                questions_models.append(QuestionModel(**q_dict))
            except Exception as e_val: # Pydantic ValidationError
                _qb_crud_logger.warning(
                    f"题库 '{difficulty.value}' 中题目数据验证失败: {q_dict}, 错误: {e_val}"
                )
                # 根据策略，可以选择跳过此题或使整个加载失败
        
        # 确保元数据中的 total_questions 与实际加载的题目数量一致
        if meta.total_questions != len(questions_models):
            _qb_crud_logger.warning(
                f"题库 '{meta.id}' 元数据中的 total_questions ({meta.total_questions}) "
                f"与实际加载的有效题目数量 ({len(questions_models)}) 不符。 "
                f"将使用实际加载数量。"
            )
            meta.total_questions = len(questions_models)
            # (可选) 如果需要，可以异步更新 index.json 文件中的 total_questions
            # await self.update_library_metadata(meta) # 需要实现此方法
        
        return QuestionBank(metadata=meta, questions=questions_models)

    async def add_question_to_bank(
        self,
        difficulty: DifficultyLevel,
        question_model_data: QuestionModel # 传入Pydantic模型实例
    ) -> Optional[QuestionModel]:
        """
        向指定难度的题库添加新题目。
        这会更新对应的题库JSON文件和 library/index.json 中的总题数。
        """
        difficulty_id = difficulty.value
        current_content = await self._read_question_bank_file_content_internal(difficulty_id)
        
        # question_model_data 已经是 QuestionModel 实例，直接 model_dump
        current_content.append(question_model_data.model_dump())
        
        if await self._write_question_bank_file_content_internal(difficulty_id, current_content):
            # 更新 index.json 中的 total_questions
            index_data = await self._read_library_index_internal()
            index_updated = False
            for item in index_data:
                if item.get("id") == difficulty_id:
                    item["total_questions"] = len(current_content)
                    index_updated = True
                    break
            if index_updated:
                await self._write_library_index_internal(index_data)
            else:
                _qb_crud_logger.warning(
                    f"为题库 '{difficulty_id}' 添加题目后，未能更新其在索引中的总题数。"
                    "可能是索引中尚无此题库的条目。"
                )
            
            # 此处不再直接调用 paper_db_handler.reload_question_bank_for_difficulty
            # 重载逻辑应由API路由层在调用此方法后，再调用PaperCRUD的重载方法。
            _qb_crud_logger.info(f"题目已添加到题库文件 '{difficulty_id}.json'。")
            return question_model_data # 返回传入的Pydantic模型实例
        
        _qb_crud_logger.error(f"向题库 '{difficulty_id}.json' 添加题目失败（文件写入错误）。")
        return None

    async def delete_question_from_bank(
        self,
        difficulty: DifficultyLevel,
        question_index: int
    ) -> Optional[Dict[str, Any]]:
        """
        从指定难度的题库中按索引删除题目，并更新索引文件。
        返回被删除的题目数据字典。
        """
        difficulty_id = difficulty.value
        current_content = await self._read_question_bank_file_content_internal(difficulty_id)

        if not (0 <= question_index < len(current_content)):
            _qb_crud_logger.warning(
                f"尝试删除题库 '{difficulty_id}' 中无效的索引: {question_index}"
            )
            return None # 索引越界

        deleted_question_dict = current_content.pop(question_index)
        
        if await self._write_question_bank_file_content_internal(difficulty_id, current_content):
            # 更新 index.json
            index_data = await self._read_library_index_internal()
            index_updated = False
            for item in index_data:
                if item.get("id") == difficulty_id:
                    item["total_questions"] = len(current_content)
                    index_updated = True
                    break
            if index_updated:
                await self._write_library_index_internal(index_data)
            
            # 通知重载的责任移交给API路由层
            _qb_crud_logger.info(f"已从题库文件 '{difficulty_id}.json' 删除索引为 {question_index} 的题目。")
            return deleted_question_dict # 返回被删除的题目原始字典
        
        _qb_crud_logger.error(f"从题库 '{difficulty_id}.json' 删除题目失败（文件写入错误）。")
        return None

    # TODO: 实现管理 library/index.json 的方法:
    # async def add_library_definition(self, new_library_meta: LibraryIndexItem) -> bool:
    #   - 检查ID是否已存在
    #   - 添加到 index.json
    #   - (可选) 创建一个空的对应的 {id}.json 文件
    # async def update_library_definition(self, difficulty_id: str, meta_update: LibraryIndexItemUpdate) -> Optional[LibraryIndexItem]:
    #   - 更新 index.json 中的条目 (除了 id 和 total_questions，后者应由内容管理同步)
    # async def delete_library_definition(self, difficulty_id: str) -> bool:
    #   - 从 index.json 移除
    #   - (可选) 删除对应的 {id}.json 文件（需谨慎）

# endregion
