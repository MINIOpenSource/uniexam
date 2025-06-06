# -*- coding: utf-8 -*-
"""
JSON文件存储库实现模块。

该模块提供了 `IDataStorageRepository` 接口的一个具体实现，
它使用JSON文件作为后端存储。数据在内存中进行管理，并通过异步文件I/O操作持久化。
每个实体类型通常对应一个JSON文件。
"""

import asyncio
import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.interfaces import IDataStorageRepository

_json_repo_logger = logging.getLogger(__name__)


class JsonStorageRepository(IDataStorageRepository):
    """
    一个使用JSON文件进行持久化的数据存储库实现。
    它在内存中管理数据，并提供异步文件I/O操作。
    """

    def __init__(self, file_paths_config: Dict[str, Path], base_data_dir: Path):
        """
        初始化 JsonStorageRepository。

        参数:
            file_paths_config (Dict[str, Path]): 一个字典，将实体类型映射到它们各自的
                                                 JSON文件路径 (相对于 `base_data_dir`)。
                                                 例如: {"users": Path("users_db.json"), "papers": Path("papers_db.json")}
            base_data_dir (Path): 存储数据文件的基础目录。
        """
        self.base_data_dir = base_data_dir
        # 构建每个实体类型的完整文件路径
        self.file_paths: Dict[str, Path] = {
            entity_type: self.base_data_dir / path_suffix
            for entity_type, path_suffix in file_paths_config.items()
        }
        self.in_memory_data: Dict[str, List[Dict[str, Any]]] = {}  # 内存数据副本
        # 为每种实体类型的文件操作创建一个异步锁
        self.file_locks: Dict[str, asyncio.Lock] = {
            entity_type: asyncio.Lock() for entity_type in self.file_paths
        }
        self._load_all_data_on_startup()  # 初始化时加载所有数据

    def _load_all_data_on_startup(self) -> None:
        """在启动时从所有配置的JSON文件加载数据到内存中。"""
        for entity_type, file_path in self.file_paths.items():
            if entity_type not in self.in_memory_data:
                self.in_memory_data[entity_type] = []  # 确保实体类型的键存在

            if file_path.exists() and file_path.is_file():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):  # 期望文件内容是一个JSON数组
                            self.in_memory_data[entity_type] = data
                            _json_repo_logger.info(
                                f"成功为实体类型 '{entity_type}' 从 '{file_path}' 加载了 {len(data)} 条记录。"
                            )
                        else:
                            _json_repo_logger.warning(
                                f"文件 '{file_path}' (实体类型 '{entity_type}') 的数据不是列表格式。将初始化为空列表。"
                            )
                            self.in_memory_data[entity_type] = []
                except (json.JSONDecodeError, IOError) as e:
                    _json_repo_logger.error(
                        f"为实体类型 '{entity_type}' 从 '{file_path}' 加载数据失败: {e}。将初始化为空列表。"
                    )
                    self.in_memory_data[entity_type] = []
            else:
                _json_repo_logger.info(
                    f"实体类型 '{entity_type}' 的文件在 '{file_path}' 未找到。将初始化为空列表。"
                )
                self.in_memory_data[entity_type] = []
                # 可选：如果希望在启动时即创建文件（即使是空的）
                # self._ensure_file_exists(entity_type, file_path) # (这是一个异步方法，此处调用需注意)

    async def _persist_data_to_file(self, entity_type: str) -> bool:
        """将指定实体类型的内存数据异步持久化到其JSON文件。"""
        if entity_type not in self.file_paths:
            _json_repo_logger.error(f"尝试持久化未知的实体类型 '{entity_type}'。")
            return False

        file_path = self.file_paths[entity_type]
        lock = self.file_locks.get(entity_type)
        if not lock:  # 如果实体类型是动态添加的，锁可能尚未创建
            _json_repo_logger.warning(
                f"实体类型 '{entity_type}' 的文件锁未找到，可能是一个新的动态实体类型。"
            )
            return False

        async with lock:
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)  # 确保父目录存在
                # 使用深拷贝以防止在异步写入过程中内存数据被修改
                data_to_write = copy.deepcopy(self.in_memory_data.get(entity_type, []))
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data_to_write, f, indent=4, ensure_ascii=False)
                _json_repo_logger.debug(  # 日志级别改为debug以减少频繁操作时的日志噪音
                    f"成功持久化实体类型 '{entity_type}' 的数据到 '{file_path}'。"
                )
                return True
            except Exception as e:  # 捕获所有可能的写入错误
                _json_repo_logger.error(
                    f"持久化实体类型 '{entity_type}' 的数据到 '{file_path}' 失败: {e}",
                    exc_info=True,  # 记录完整的异常信息
                )
                return False

    async def connect(self) -> None:
        """建立与数据存储的连接。对于JSON文件存储，此操作为空操作。"""
        _json_repo_logger.info("JsonStorageRepository: 'connect' 被调用 (空操作)。")
        pass

    async def disconnect(self) -> None:
        """关闭与数据存储的连接。对于JSON文件存储，此操作为空操作。"""
        _json_repo_logger.info("JsonStorageRepository: 'disconnect' 被调用 (空操作)。")
        pass

    async def get_by_id(
        self, entity_type: str, entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """根据ID从内存中检索单个实体。"""
        if entity_type not in self.in_memory_data:
            _json_repo_logger.warning(
                f"尝试按ID获取实体，但实体类型 '{entity_type}' 不在内存数据中。"
            )
            return None

        # 假设 'id' 字段是标准的，或者需要一种方式来指定ID字段。
        # (Assuming the 'id' field is standard, or a way to specify the ID field is needed.)
        # 为了简化和通用性，这里假设ID字段是 'id', 'uid', 或 'paper_id' 等。
        # 在更复杂的场景下，可能需要为每种实体类型指定主键字段名。
        id_fields_to_check = [
            "id",
            f"{entity_type}_id",
            "uid",
            "paper_id",
        ]  # 常见的ID字段名

        for item in self.in_memory_data[entity_type]:
            for id_field in id_fields_to_check:
                if id_field in item and str(item[id_field]) == str(entity_id):
                    return copy.deepcopy(item)  # 返回深拷贝以防止外部修改内存数据
        return None

    async def get_all(
        self, entity_type: str, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """检索指定类型的所有实体（内存中的副本），支持分页。"""
        if entity_type not in self.in_memory_data:
            _json_repo_logger.warning(
                f"尝试获取所有实体，但实体类型 '{entity_type}' 不在内存数据中。"
            )
            return []

        all_items = self.in_memory_data[entity_type]
        # 对内存中的列表进行切片以实现分页
        return copy.deepcopy(all_items[skip : skip + limit])

    async def create(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """在内存中创建新实体并异步持久化到文件。"""
        if entity_type not in self.in_memory_data:
            # 如果实体类型是首次遇到，则在内存和文件路径配置中初始化它
            self.in_memory_data[entity_type] = []
            if entity_type not in self.file_paths:
                # 为新的实体类型定义一个默认的文件名规则
                self.file_paths[entity_type] = (
                    self.base_data_dir / f"{entity_type}_db.json"
                )
                self.file_locks[entity_type] = asyncio.Lock()  # 并为其创建文件锁
                _json_repo_logger.info(
                    f"实体类型 '{entity_type}' 为新类型，已使用默认路径 '{self.file_paths[entity_type]}' 进行初始化。"
                )

        # 检查ID是否已存在，以避免重复创建 (依赖于 get_by_id 和ID字段的约定)
        # 此处假设ID字段存在于entity_data中，或者get_by_id可以处理
        temp_id_fields = ["id", "uid", "paper_id", f"{entity_type}_id"]
        entity_id_val = None
        for id_field_key in temp_id_fields:
            if id_field_key in entity_data:
                entity_id_val = str(entity_data[id_field_key])
                break

        if entity_id_val and await self.get_by_id(entity_type, entity_id_val):
            _json_repo_logger.error(
                f"尝试创建重复的实体: 类型='{entity_type}', ID='{entity_id_val}'"
            )
            raise ValueError(
                f"实体类型 '{entity_type}' 中 ID 为 '{entity_id_val}' 的实体已存在。"
            )

        new_entity = copy.deepcopy(entity_data)
        self.in_memory_data[entity_type].append(new_entity)  # 添加到内存列表
        await self._persist_data_to_file(entity_type)  # 异步持久化到文件
        return new_entity

    async def update(
        self, entity_type: str, entity_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """根据ID更新内存中的现有实体，并异步持久化更改。"""
        if entity_type not in self.in_memory_data:
            _json_repo_logger.warning(
                f"尝试更新实体，但实体类型 '{entity_type}' 不存在于内存中。"
            )
            return None

        id_fields_to_check = ["id", f"{entity_type}_id", "uid", "paper_id"]
        found_idx = -1  # 初始化找到的索引为-1

        # 遍历查找具有匹配ID的实体
        for i, item in enumerate(self.in_memory_data[entity_type]):
            for id_field in id_fields_to_check:
                if id_field in item and str(item[id_field]) == str(entity_id):
                    found_idx = i
                    break
            if found_idx != -1:
                break

        if found_idx != -1:
            entity_to_update = self.in_memory_data[entity_type][found_idx]
            entity_to_update.update(update_data)  # 执行部分更新
            self.in_memory_data[entity_type][
                found_idx
            ] = entity_to_update  # 更新内存中的记录
            await self._persist_data_to_file(entity_type)  # 异步持久化
            return copy.deepcopy(entity_to_update)

        _json_repo_logger.warning(
            f"尝试更新实体，但在实体类型 '{entity_type}' 中未找到ID为 '{entity_id}' 的实体。"
        )
        return None

    async def delete(self, entity_type: str, entity_id: str) -> bool:
        """根据ID从内存中删除实体，并异步持久化更改。"""
        if entity_type not in self.in_memory_data:
            _json_repo_logger.warning(
                f"尝试删除实体，但实体类型 '{entity_type}' 不存在于内存中。"
            )
            return False

        id_fields_to_check = ["id", f"{entity_type}_id", "uid", "paper_id"]
        # initial_len = len(self.in_memory_data[entity_type]) # 未使用 (Unused)

        # 构建一个不包含待删除项的新列表
        items_to_keep = []
        item_deleted = False
        for item in self.in_memory_data[entity_type]:
            is_match = False
            for id_field in id_fields_to_check:
                if id_field in item and str(item[id_field]) == str(entity_id):
                    is_match = True
                    break
            if not is_match:
                items_to_keep.append(item)
            else:
                item_deleted = True

        if item_deleted:
            self.in_memory_data[entity_type] = items_to_keep
            await self._persist_data_to_file(entity_type)  # 异步持久化
        return item_deleted

    async def query(
        self,
        entity_type: str,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """根据一组条件从内存中查询实体。"""
        if entity_type not in self.in_memory_data:
            _json_repo_logger.warning(
                f"尝试查询实体，但实体类型 '{entity_type}' 不存在于内存中。"
            )
            return []

        results: List[Dict[str, Any]] = []
        # 在内存中进行简单过滤
        for item in self.in_memory_data[entity_type]:
            match = True
            for key, value in conditions.items():
                if item.get(key) != value:  # 精确匹配
                    match = False
                    break
            if match:
                results.append(item)

        # 对过滤后的结果应用分页
        return copy.deepcopy(results[skip : skip + limit])

    async def _ensure_file_exists(
        self,
        entity_type: str,
        file_path: Path,
        initial_data: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """确保JSON文件存在，如果不存在则创建并用空列表或提供的初始数据初始化。"""
        lock = self.file_locks.get(entity_type)  # 获取对应实体类型的锁
        if not lock:
            # 对于动态添加的实体类型，可能需要动态创建锁
            _json_repo_logger.warning(
                f"为实体类型 '{entity_type}' 获取文件锁失败，可能未正确初始化。"
            )
            return  # 或者抛出错误

        async with lock:
            if not file_path.exists():  # 检查文件是否存在
                file_path.parent.mkdir(parents=True, exist_ok=True)  # 确保父目录存在
                data_to_write = (
                    initial_data if initial_data is not None else []
                )  # 确定写入内容
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(data_to_write, f, indent=4, ensure_ascii=False)
                    _json_repo_logger.info(
                        f"已为实体类型 '{entity_type}' 在 '{file_path}' 初始化JSON文件。"
                    )
                except IOError as e:
                    _json_repo_logger.error(
                        f"为实体类型 '{entity_type}' 在 '{file_path}' 创建初始文件失败: {e}"
                    )

    async def init_storage_if_needed(
        self, entity_type: str, initial_data: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        确保给定实体类型的存储已初始化。
        对于JSON存储库，这意味着对应的JSON文件已创建。
        """
        if entity_type not in self.file_paths:
            # 如果实体类型未在初始配置中定义，则为其创建一个默认文件路径和锁
            default_path = self.base_data_dir / f"{entity_type}_default_db.json"
            self.file_paths[entity_type] = default_path
            self.file_locks[entity_type] = asyncio.Lock()  # 为新实体类型创建锁
            _json_repo_logger.warning(
                f"实体类型 '{entity_type}' 无预设文件路径，已默认设置为 '{default_path}'。"
            )

        file_path = self.file_paths[entity_type]

        # 确保内存中存在该实体类型的列表
        if entity_type not in self.in_memory_data:
            self.in_memory_data[entity_type] = []

        # 如果文件不存在，则创建并用初始数据（或空列表）填充
        if not file_path.exists():
            await self._ensure_file_exists(entity_type, file_path, initial_data or [])
            # 如果提供了初始数据且内存中为空，则用初始数据填充内存
            # （_load_all_data_on_startup 应该在之后或之前处理了加载逻辑，这里确保创建时一致性）
            if initial_data and not self.in_memory_data[entity_type]:
                self.in_memory_data[entity_type] = copy.deepcopy(initial_data)
        elif (
            initial_data and not self.in_memory_data[entity_type]
        ):  # 文件存在，但内存为空，且提供了初始数据
            # 此逻辑分支可能需要根据具体需求调整。
            # 当前：如果文件存在，数据在启动时已加载。此方法主要确保文件创建。
            # 如果希望用 initial_data 覆盖或填充空文件后的内存，需要更复杂的逻辑。
            _json_repo_logger.debug(
                f"实体类型 '{entity_type}' 的文件已存在，内存为空但提供了初始数据。依赖启动时加载。"
            )
            pass

    async def get_all_entity_types(self) -> List[str]:
        """返回此存储库当前在内存中管理的所有实体类型的列表。"""
        return list(self.in_memory_data.keys())

    async def persist_all_data(self) -> None:
        """将所有实体类型的内存数据异步持久化到各自的JSON文件。"""
        _json_repo_logger.info("尝试持久化所有实体类型的数据...")
        for entity_type in list(
            self.in_memory_data.keys()
        ):  # 使用 list() 避免在迭代时修改字典
            await self._persist_data_to_file(entity_type)
        _json_repo_logger.info("所有数据持久化完成。")


__all__ = ["JsonStorageRepository"]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行
    print(f"此模块 ({__name__}) 定义了JSON存储库，不应直接执行。")
