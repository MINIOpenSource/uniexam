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

# 常见的ID字段名列表，用于自动索引
# (List of common ID field names for automatic indexing)
COMMON_ID_FIELDS = ["id", "uid", "paper_id"]


class JsonStorageRepository(IDataStorageRepository):
    """
    一个使用JSON文件进行持久化的数据存储库实现。
    它在内存中管理数据，并提供异步文件I/O操作。
    此实现包含对常见ID字段的内存索引，以加速 `get_by_id` 操作。

    性能提示 (Performance Notes):
    - `get_by_id`: 如果查询的ID字段被索引 (见 `COMMON_ID_FIELDS`)，则查找速度非常快 (O(1))。
                   否则，如果需要回退到线性扫描 (当前未实现回退)，则为 O(n)。
    - `create`, `delete`: 除了文件I/O，还包括对索引的更新，通常很快。
    - `update`: 如果ID不变且直接修改内存中的对象引用，索引不需要更新。
    - `query`, `get_all`: 这些操作目前依赖于Python的列表迭代和字典比较，
                         对于大型数据集，其性能可能不如数据库的查询引擎。
    - `_persist_data_to_file`: **重要**: 此方法在每次创建、更新或删除操作后重写整个JSON文件。
                               对于频繁写入或大型数据集，这可能成为严重的性能瓶颈，并增加I/O负载。
                               考虑使用更高级的数据存储方案（如SQLite、NoSQL数据库）或更复杂的
                               文件更新策略（例如，仅追加日志式的更改，定期压缩文件）以优化性能。
    """

    def __init__(self, file_paths_config: Dict[str, Path], base_data_dir: Path):
        """
        初始化 JsonStorageRepository。
        (Initializes the JsonStorageRepository.)

        参数 (Args):
            file_paths_config (Dict[str, Path]): 一个字典，将实体类型映射到它们各自的
                                                 JSON文件路径 (相对于 `base_data_dir`)。
                                                 (A dictionary mapping entity types to their respective
                                                  JSON file paths (relative to `base_data_dir`).)
            base_data_dir (Path): 存储数据文件的基础目录。
                                  (The base directory for storing data files.)
        """
        self.base_data_dir = base_data_dir
        self.file_paths: Dict[str, Path] = {
            entity_type: self.base_data_dir / path_suffix
            for entity_type, path_suffix in file_paths_config.items()
        }
        self.in_memory_data: Dict[str, List[Dict[str, Any]]] = {}
        # 内存ID索引: {entity_type: {id_field_name: {entity_id_value: entity_object_reference}}}
        # (In-memory ID index: {entity_type: {id_field_name: {entity_id_value: entity_object_reference}}})
        self.id_indexes: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # 为每种预定义实体类型的文件操作创建一个异步锁
        # (Create an async lock for file operations for each predefined entity type)
        self.file_locks: Dict[str, asyncio.Lock] = {
            entity_type: asyncio.Lock() for entity_type in self.file_paths
        }
        # 注意: 如果后续通过 `create` 方法动态添加新的实体类型，
        #       需要确保也为这些新类型创建锁 (已在 `create` 方法中处理)。
        # (Note: If new entity types are dynamically added via the `create` method,
        #  ensure locks are also created for these new types (handled in `create` method).)

        self._load_all_data_on_startup()  # 初始化时加载所有数据并构建索引
        # (Load all data and build indexes on initialization)

    def _build_id_indexes(self, entity_type: str) -> None:
        """
        为指定的实体类型构建内存ID索引。
        (Builds in-memory ID indexes for the specified entity type.)

        此方法会遍历实体类型的数据，并为 `COMMON_ID_FIELDS` 中定义的每个ID字段创建索引。
        (This method iterates through the data of an entity type and creates an index
         for each ID field defined in `COMMON_ID_FIELDS`.)

        参数 (Args):
            entity_type (str): 要为其构建索引的实体类型。
                               (The entity type for which to build indexes.)
        """
        _json_repo_logger.debug(f"开始为实体类型 '{entity_type}' 构建ID索引。")
        # 清除该实体类型现有的所有ID字段索引 (Clear all existing ID field indexes for this entity type)
        self.id_indexes[entity_type] = {}

        if (
            entity_type not in self.in_memory_data
            or not self.in_memory_data[entity_type]
        ):
            _json_repo_logger.debug(f"实体类型 '{entity_type}' 无数据，跳过索引构建。")
            return

        for item in self.in_memory_data[entity_type]:
            for id_field_name in COMMON_ID_FIELDS:
                if id_field_name in item:
                    entity_id_value = str(
                        item[id_field_name]
                    )  # 确保ID值为字符串 (Ensure ID value is string)

                    # 如果该ID字段的索引尚未初始化，则创建它
                    # (If the index for this ID field hasn't been initialized, create it)
                    if id_field_name not in self.id_indexes[entity_type]:
                        self.id_indexes[entity_type][id_field_name] = {}

                    # 添加到索引，值为对内存中实际对象的引用
                    # (Add to index, value is a reference to the actual object in memory)
                    self.id_indexes[entity_type][id_field_name][entity_id_value] = item

        indexed_fields_count = {
            field: len(idx) for field, idx in self.id_indexes[entity_type].items()
        }
        _json_repo_logger.info(
            f"为实体类型 '{entity_type}' 构建ID索引完成。索引字段及条目数: {indexed_fields_count}"
        )

    def _load_all_data_on_startup(self) -> None:
        """在启动时从所有配置的JSON文件加载数据到内存中，并为每个实体类型构建ID索引。"""
        for entity_type, file_path in self.file_paths.items():
            if entity_type not in self.in_memory_data:
                self.in_memory_data[entity_type] = []

            if file_path.exists() and file_path.is_file():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
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

            # 为加载的数据构建索引 (Build indexes for the loaded data)
            self._build_id_indexes(entity_type)

    async def _persist_data_to_file(self, entity_type: str) -> bool:
        """
        将指定实体类型的内存数据异步持久化到其JSON文件。
        (Persists in-memory data of the specified entity type to its JSON file asynchronously.)

        性能警告 (Performance Warning):
            此方法会重写实体类型的整个JSON文件。对于频繁写入或大型数据集，
            这可能成为一个显著的性能瓶颈，并可能导致大量的磁盘I/O。
            在生产环境中，应考虑更健壮的数据存储解决方案或优化写入策略。
            (This method rewrites the entire JSON file for the entity type. For frequent writes
             or large datasets, this can become a significant performance bottleneck and may
             lead to substantial disk I/O. In production environments, consider more robust
             data storage solutions or optimized writing strategies.)
        """
        if entity_type not in self.file_paths:
            _json_repo_logger.error(f"尝试持久化未知的实体类型 '{entity_type}'。")
            return False

        file_path = self.file_paths[entity_type]
        lock = self.file_locks.get(entity_type)
        if not lock:
            _json_repo_logger.warning(
                f"实体类型 '{entity_type}' 的文件锁未找到，可能是一个新的动态实体类型。"
            )
            return False

        async with lock:
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                data_to_write = copy.deepcopy(self.in_memory_data.get(entity_type, []))
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data_to_write, f, indent=4, ensure_ascii=False)
                _json_repo_logger.debug(
                    f"成功持久化实体类型 '{entity_type}' 的数据到 '{file_path}'。"
                )
                return True
            except Exception as e:
                _json_repo_logger.error(
                    f"持久化实体类型 '{entity_type}' 的数据到 '{file_path}' 失败: {e}",
                    exc_info=True,
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
        """
        根据ID从内存中检索单个实体，优先使用ID索引。
        (Retrieves a single entity from memory by ID, prioritizing ID indexes.)
        """
        if entity_type not in self.id_indexes:
            _json_repo_logger.warning(
                f"尝试通过ID获取实体，但实体类型 '{entity_type}' 的索引不存在。可能需要先加载数据或该类型无数据。"
            )
            if entity_type in self.in_memory_data:
                _json_repo_logger.debug(
                    f"实体类型 '{entity_type}' 索引缺失，尝试线性扫描..."
                )
                for item in self.in_memory_data[entity_type]:
                    for id_field_name in COMMON_ID_FIELDS:
                        if id_field_name in item and str(item[id_field_name]) == str(
                            entity_id
                        ):
                            return copy.deepcopy(item)
            return None

        entity_id_str = str(entity_id)

        for id_field_name, id_map in self.id_indexes[entity_type].items():
            if id_field_name in COMMON_ID_FIELDS:
                indexed_item = id_map.get(entity_id_str)
                if indexed_item is not None:
                    _json_repo_logger.debug(
                        f"实体 '{entity_type}/{entity_id_str}' 通过索引字段 '{id_field_name}' 找到。"
                    )
                    return copy.deepcopy(indexed_item)

        _json_repo_logger.debug(
            f"实体 '{entity_type}/{entity_id_str}' 在ID索引中未找到。考虑它是否使用非标准ID字段或确实不存在。"
        )
        return None

    async def get_all(
        self, entity_type: str, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        检索指定类型的所有实体（内存中的副本），支持分页。
        性能提示：此操作直接对内存列表进行切片，对于非常大的列表，深拷贝成本可能较高。
        (Retrieves all entities of a specified type (in-memory copies), supports pagination.
         Performance note: This operation slices the in-memory list directly; deepcopy cost might be high for very large lists.)
        """
        if entity_type not in self.in_memory_data:
            _json_repo_logger.warning(
                f"尝试获取所有实体，但实体类型 '{entity_type}' 不在内存数据中。"
            )
            return []

        all_items = self.in_memory_data[entity_type]
        return copy.deepcopy(all_items[skip : skip + limit])

    async def create(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """在内存中创建新实体，更新ID索引，并异步持久化到文件。"""
        if entity_type not in self.in_memory_data:
            self.in_memory_data[entity_type] = []
            self.id_indexes[entity_type] = {}
            if entity_type not in self.file_paths:
                self.file_paths[entity_type] = (
                    self.base_data_dir / f"{entity_type}_db.json"
                )
                self.file_locks[entity_type] = asyncio.Lock()
                _json_repo_logger.info(
                    f"实体类型 '{entity_type}' 为新类型，已使用默认路径 '{self.file_paths[entity_type]}' 进行初始化。"
                )

        new_entity_id_val_str: Optional[str] = None

        for id_field_name in COMMON_ID_FIELDS:
            if id_field_name in entity_data:
                new_entity_id_val_str = str(entity_data[id_field_name])
                if (
                    self.id_indexes[entity_type]
                    .get(id_field_name, {})
                    .get(new_entity_id_val_str)
                ):
                    _json_repo_logger.error(
                        f"尝试使用已存在的ID创建重复实体: 类型='{entity_type}', 字段='{id_field_name}', ID='{new_entity_id_val_str}'"
                    )
                    raise ValueError(
                        f"实体类型 '{entity_type}' 中，字段 '{id_field_name}' 的 ID 为 '{new_entity_id_val_str}' 的实体已存在。"
                    )
                break

        new_entity = copy.deepcopy(entity_data)
        self.in_memory_data[entity_type].append(new_entity)

        for id_field_name in COMMON_ID_FIELDS:
            if id_field_name in new_entity:
                entity_id_value = str(new_entity[id_field_name])
                if id_field_name not in self.id_indexes[entity_type]:
                    self.id_indexes[entity_type][id_field_name] = {}
                self.id_indexes[entity_type][id_field_name][entity_id_value] = (
                    new_entity
                )

        await self._persist_data_to_file(entity_type)
        return new_entity

    async def update(
        self, entity_type: str, entity_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        根据ID更新内存中的现有实体，并异步持久化更改。
        假设ID字段本身不被修改。如果ID字段可变，则需要更复杂的索引更新逻辑（删除旧索引，添加新索引）。
        (Updates an existing entity in memory by ID and persists changes asynchronously.
         Assumes ID fields themselves are not modified. If ID fields are mutable,
         more complex index update logic (remove old index, add new index) would be required.)
        """
        entity_to_update = await self.get_by_id(entity_type, entity_id)  # type: ignore

        if entity_to_update:
            actual_item_reference = None

            entity_id_str = str(entity_id)
            found_via_index = False
            for id_field_name, id_map in self.id_indexes.get(entity_type, {}).items():
                if id_field_name in COMMON_ID_FIELDS:
                    indexed_item_ref = id_map.get(entity_id_str)
                    if indexed_item_ref is not None:
                        actual_item_reference = indexed_item_ref
                        found_via_index = True
                        break

            if not found_via_index:
                _json_repo_logger.warning(
                    f"更新 '{entity_type}/{entity_id_str}': 索引未命中，尝试线性扫描获取引用（罕见）。"
                )
                for _i, item_in_list in enumerate(  # B007: Renamed i to _i
                    self.in_memory_data.get(entity_type, [])
                ):
                    for id_field in COMMON_ID_FIELDS:
                        if (
                            id_field in item_in_list
                            and str(item_in_list[id_field]) == entity_id_str
                        ):
                            actual_item_reference = item_in_list
                            break
                    if actual_item_reference:
                        break

            if actual_item_reference:
                for id_field_name in COMMON_ID_FIELDS:
                    if id_field_name in update_data and str(
                        update_data[id_field_name]
                    ) != str(actual_item_reference.get(id_field_name)):
                        _json_repo_logger.error(
                            f"禁止通过 update 方法修改ID字段 '{id_field_name}' (ID field '{id_field_name}' modification via update method is prohibited)."
                        )
                        raise ValueError(
                            f"不允许通过此 update 方法修改ID字段 '{id_field_name}'。"
                        )

                actual_item_reference.update(update_data)
                await self._persist_data_to_file(entity_type)
                return copy.deepcopy(actual_item_reference)

        _json_repo_logger.warning(
            f"尝试更新实体，但在实体类型 '{entity_type}' 中未找到ID为 '{entity_id}' 的实体。"
        )
        return None

    async def delete(self, entity_type: str, entity_id: str) -> bool:
        """根据ID从内存中删除实体，从ID索引中移除，并异步持久化更改。"""
        if entity_type not in self.in_memory_data:
            _json_repo_logger.warning(
                f"尝试删除实体，但实体类型 '{entity_type}' 不存在于内存中。"
            )
            return False

        entity_id_str = str(entity_id)
        item_to_delete = None
        item_index_in_list = -1

        for id_field_name, id_map in self.id_indexes.get(entity_type, {}).items():
            if id_field_name in COMMON_ID_FIELDS:
                item_to_delete = id_map.get(entity_id_str)
                if item_to_delete is not None:
                    break

        item_deleted_from_list = False
        if item_to_delete:
            try:
                self.in_memory_data[entity_type].remove(item_to_delete)
                item_deleted_from_list = True
            except ValueError:
                _json_repo_logger.error(
                    f"删除 '{entity_type}/{entity_id_str}': 索引找到但对象不在主数据列表中。索引可能已损坏。"
                )
                item_deleted_from_list = False

        if not item_to_delete or not item_deleted_from_list:
            _json_repo_logger.debug(
                f"删除 '{entity_type}/{entity_id_str}': 索引未命中或列表移除失败，尝试线性扫描。"
            )
            for i, item_in_list in enumerate(self.in_memory_data.get(entity_type, [])):
                for id_field in COMMON_ID_FIELDS:
                    if (
                        id_field in item_in_list
                        and str(item_in_list[id_field]) == entity_id_str
                    ):
                        item_to_delete = item_in_list
                        item_index_in_list = i
                        break
                if (
                    item_to_delete and item_index_in_list != -1
                ):  # Check if found in this scan pass
                    break
            if item_index_in_list != -1:  # If found via linear scan
                self.in_memory_data[entity_type].pop(item_index_in_list)
                item_deleted_from_list = True  # Now it's deleted from list

        if item_to_delete and item_deleted_from_list:
            for id_field_name, id_map in self.id_indexes.get(entity_type, {}).items():
                if id_field_name in item_to_delete:
                    id_val_of_deleted = str(item_to_delete[id_field_name])
                    if id_val_of_deleted in id_map:
                        del id_map[id_val_of_deleted]

            await self._persist_data_to_file(entity_type)
            _json_repo_logger.info(
                f"成功删除并持久化实体 '{entity_type}/{entity_id_str}'。"
            )
            return True

        _json_repo_logger.warning(
            f"尝试删除实体，但在实体类型 '{entity_type}' 中未找到ID为 '{entity_id_str}' 的实体。"
        )
        return False

    async def query(
        self,
        entity_type: str,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        根据一组条件从内存中查询实体。
        性能提示：此查询为线性扫描，对于大型数据集可能较慢。
        (Queries entities from memory based on a set of conditions.
         Performance note: This query is a linear scan and may be slow for large datasets.)
        """
        if entity_type not in self.in_memory_data:
            _json_repo_logger.warning(
                f"尝试查询实体，但实体类型 '{entity_type}' 不在内存数据中。"
            )
            return []

        results: List[Dict[str, Any]] = []
        for item in self.in_memory_data[entity_type]:
            match = True
            for key, value in conditions.items():
                if item.get(key) != value:
                    match = False
                    break
            if match:
                results.append(item)

        return copy.deepcopy(results[skip : skip + limit])

    async def _ensure_file_exists(
        self,
        entity_type: str,
        file_path: Path,
        initial_data: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """确保JSON文件存在，如果不存在则创建并用空列表或提供的初始数据初始化。"""
        lock = self.file_locks.get(entity_type)
        if not lock:
            _json_repo_logger.warning(
                f"为实体类型 '{entity_type}' 获取文件锁失败，可能未正确初始化。"
            )
            return

        async with lock:
            if not file_path.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)
                data_to_write = initial_data if initial_data is not None else []
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
            default_path = self.base_data_dir / f"{entity_type}_default_db.json"
            self.file_paths[entity_type] = default_path
            self.file_locks[entity_type] = asyncio.Lock()
            _json_repo_logger.warning(
                f"实体类型 '{entity_type}' 无预设文件路径，已默认设置为 '{default_path}'。"
            )

        file_path = self.file_paths[entity_type]

        if entity_type not in self.in_memory_data:
            self.in_memory_data[entity_type] = []

        if not file_path.exists():
            await self._ensure_file_exists(entity_type, file_path, initial_data or [])
            if initial_data and not self.in_memory_data[entity_type]:
                self.in_memory_data[entity_type] = copy.deepcopy(initial_data)
        elif initial_data and not self.in_memory_data[entity_type]:
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
        for entity_type in list(self.in_memory_data.keys()):
            await self._persist_data_to_file(entity_type)
        _json_repo_logger.info("所有数据持久化完成。")


__all__ = ["JsonStorageRepository"]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行
    print(f"此模块 ({__name__}) 定义了JSON存储库，不应直接执行。")
