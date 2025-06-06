# -*- coding: utf-8 -*-
"""
Redis 数据存储库实现模块。
(Redis Data Storage Repository Implementation Module.)

该模块提供了 `IDataStorageRepository` 接口的一个具体实现，
使用 Redis 作为后端数据存储。实体被序列化为 JSON 字符串进行存储。
它还使用 Redis Set 来管理每种实体类型的所有ID，以便支持 `get_all` 和简单查询。
(This module provides a concrete implementation of the `IDataStorageRepository` interface,
using Redis as the backend data store. Entities are serialized as JSON strings for storage.
It also uses Redis Sets to manage all IDs for each entity type, to support `get_all`
and simple queries.)
"""

import json  # 用于JSON序列化和反序列化 (For JSON serialization and deserialization)
import logging
from typing import Any, Dict, List, Optional

import aioredis  # type: ignore # aioredis 可能没有完整的类型存根 (aioredis might not have complete type stubs)

from app.core.interfaces import (
    IDataStorageRepository,
)  # 导入抽象基类 (Import abstract base class)

from .qb_crud import (
    QB_CONTENT_ENTITY_TYPE_PREFIX,
)  # 用于键名构造 (For key name construction)

_redis_repo_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例

# Redis键名前缀或模式定义 (Redis key prefix or pattern definitions)
USER_KEY_PREFIX = "user"  # 用户实体键名前缀 (User entity key prefix)
PAPER_KEY_PREFIX = "paper"  # 试卷实体键名前缀 (Paper entity key prefix)
QB_METADATA_KEY_PREFIX = (
    "qb_meta"  # 题库元数据键名前缀 (Question bank metadata key prefix)
)
ENTITY_IDS_SET_KEY_PREFIX = "entity_ids"  # 存储各类实体ID集合的键名前缀 (Key prefix for sets storing entity IDs)


class RedisStorageRepository(IDataStorageRepository):
    """
    一个使用 Redis 进行持久化的数据存储库实现。
    实体作为JSON字符串存储。同时，为每种实体类型管理一个ID集合，
    以支持 `get_all` 和简单的 `query` 操作。
    (A data storage repository implementation using Redis for persistence.
    Entities are stored as JSON strings. Additionally, an ID set is managed for each
    entity type to support `get_all` and simple `query` operations.)
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,  # 例如 (e.g.): "redis://localhost:6379/0"
        host: str = "localhost",  # Redis 服务器主机名 (Redis server hostname)
        port: int = 6379,  # Redis 服务器端口 (Redis server port)
        db: int = 0,  # Redis 数据库编号 (Redis database number)
        password: Optional[
            str
        ] = None,  # Redis 连接密码 (可选) (Redis connection password (optional))
    ):
        """
        初始化 RedisStorageRepository。
        (Initializes the RedisStorageRepository.)

        参数 (Args):
            redis_url (Optional[str]): Redis 连接URL。如果提供，则优先使用此URL。
                                       (Redis connection URL. If provided, this URL is used preferentially.)
            host (str): Redis 服务器主机名。默认为 'localhost'。
                        (Redis server hostname. Defaults to 'localhost'.)
            port (int): Redis 服务器端口。默认为 6379。
                        (Redis server port. Defaults to 6379.)
            db (int): Redis 数据库编号。默认为 0。
                      (Redis database number. Defaults to 0.)
            password (Optional[str]): Redis 连接密码 (如果需要)。
                                      (Redis connection password (if required).)
        """
        if redis_url:
            self.redis_url = redis_url
        else:  # 根据单独参数构建连接URL (Construct connection URL from individual parameters)
            auth_part = f":{password}@" if password else ""
            self.redis_url = f"redis://{auth_part}{host}:{port}/{db}"

        self.redis: Optional[aioredis.Redis] = (
            None  # aioredis连接实例 (aioredis connection instance)
        )
        _redis_repo_logger.info(
            "RedisStorageRepository 已初始化。 (RedisStorageRepository initialized.)"
        )

    def _get_entity_key(self, entity_type: str, entity_id: str) -> str:
        """
        根据实体类型和ID生成用于Redis的键名。
        (Generates a Redis key name based on entity type and ID.)
        例如 (e.g.): "user:user123", "paper:paper_abc", "qb_content_easy:easy"
        """
        # 对于题库内容这类有特定前缀的实体类型，键名构造可能不同
        # (For entity types with specific prefixes like question bank content, key construction might differ)
        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
            # entity_id 对于 qb_content 已经是 difficulty_id
            # (entity_id for qb_content is already difficulty_id)
            return f"{entity_type}:{entity_id}"  # 例如 "qb_content_easy:easy"
        return f"{entity_type}:{entity_id}"  # 通用格式 (General format)

    def _get_entity_ids_set_key(self, entity_type: str) -> str:
        """
        为给定实体类型生成存储其所有ID的Redis Set的键名。
        (Generates the Redis Set key name for storing all IDs of a given entity type.)
        例如 (e.g.): "entity_ids:user", "entity_ids:paper", "entity_ids:qb_content_easy"
        """
        return f"{ENTITY_IDS_SET_KEY_PREFIX}:{entity_type}"

    async def connect(self) -> None:
        """建立与Redis服务器的连接。(Establishes a connection to the Redis server.)"""
        if self.redis and self.redis.is_connected:  # aioredis v2+
            _redis_repo_logger.info(
                "Redis 连接已建立。 (Redis connection already established.)"
            )
            return
        try:
            self.redis = aioredis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self.redis.ping()  # 测试连接 (Test connection)
            _redis_repo_logger.info(
                "Redis 连接已成功建立。 (Redis connection established successfully.)"
            )
        except Exception as e:
            _redis_repo_logger.error(
                f"建立 Redis 连接失败 (Failed to establish Redis connection): {e}",
                exc_info=True,
            )
            raise

    async def disconnect(self) -> None:
        """关闭与Redis服务器的连接。(Closes the connection to the Redis server.)"""
        if self.redis:
            await self.redis.close()
            self.redis = None
            _redis_repo_logger.info("Redis 连接已关闭。 (Redis connection closed.)")
        else:
            _redis_repo_logger.info(
                "无活动的 Redis 连接可关闭。 (No active Redis connection to close.)"
            )

    async def init_storage_if_needed(
        self, entity_type: str, default_data: Optional[Any] = None
    ) -> None:
        """
        确保给定实体类型的存储已初始化。对于Redis，此方法主要为空操作。
        (Ensures storage for the given entity type is initialized. For Redis, this is mainly a no-op.)
        """
        _redis_repo_logger.info(
            f"RedisStorageRepository: 'init_storage_if_needed' 被调用 (实体类型 (Entity Type): '{entity_type}')，此操作为空。(Called (entity type: '{entity_type}'), this is a no-op.)"
        )
        pass

    async def get_by_id(
        self, entity_type: str, entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """通过ID从Redis检索单个实体（存储为JSON字符串）。(Retrieves a single entity by ID from Redis (stored as JSON string)."""
        if not self.redis:
            await self.connect()
        assert (
            self.redis is not None
        ), "Redis连接未初始化 (Redis connection not initialized)"

        key_name = self._get_entity_key(entity_type, entity_id)
        json_string = await self.redis.get(key_name)

        if json_string:
            try:
                return json.loads(
                    json_string
                )  # 反序列化JSON字符串为字典 (Deserialize JSON string to dict)
            except json.JSONDecodeError:
                _redis_repo_logger.error(
                    f"为键 {key_name} 解码JSON失败。 (Failed to decode JSON for key {key_name}.)"
                )
                return None
        return None  # 未找到键 (Key not found)

    async def get_all(
        self, entity_type: str, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        从Redis检索指定类型的所有实体。通过获取ID集合，然后批量获取实体数据实现。分页在Python端完成。
        警告：对于非常大的数据集，此方法可能效率低下。
        (Retrieves all entities of a specified type from Redis. Implemented by fetching the ID set,
         then batch-fetching entity data. Pagination is done on the Python side.
         Warning: This method can be inefficient for very large datasets.)
        """
        if not self.redis:
            await self.connect()
        assert (
            self.redis is not None
        ), "Redis连接未初始化 (Redis connection not initialized)"

        ids_set_key = self._get_entity_ids_set_key(entity_type)
        entity_ids = list(
            await self.redis.smembers(ids_set_key)
        )  # 获取所有ID (Get all IDs)

        try:
            entity_ids.sort()  # 尝试排序以保证分页一致性 (Try sorting for consistent pagination)
        except TypeError:
            _redis_repo_logger.warning(
                f"无法为实体类型 '{entity_type}' 的ID排序，分页可能不一致。 (Cannot sort IDs for entity type '{entity_type}', pagination may be inconsistent.)"
            )

        paginated_ids = entity_ids[
            skip : skip + limit
        ]  # 在Python端进行分页 (Paginate on Python side)
        if not paginated_ids:
            return []

        keys_to_fetch = [
            self._get_entity_key(entity_type, eid) for eid in paginated_ids
        ]
        if not keys_to_fetch:
            return []

        json_strings = await self.redis.mget(*keys_to_fetch)  # 批量获取 (Batch get)
        results: List[Dict[str, Any]] = []
        for i, json_string in enumerate(json_strings):
            if json_string:
                try:
                    results.append(json.loads(json_string))
                except json.JSONDecodeError:
                    _redis_repo_logger.error(
                        f"为键 {keys_to_fetch[i]} 解码JSON失败。 (Failed to decode JSON for key {keys_to_fetch[i]}.)"
                    )
            else:
                _redis_repo_logger.warning(
                    f"在mget操作中，键 {keys_to_fetch[i]} 的数据缺失。 (Data for key {keys_to_fetch[i]} missing in mget operation.)"
                )
        return results

    async def create(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """在Redis中创建新实体（存储为JSON字符串）。(Creates a new entity in Redis (stored as JSON string)."""
        if not self.redis:
            await self.connect()
        assert (
            self.redis is not None
        ), "Redis连接未初始化 (Redis connection not initialized)"

        entity_id: str
        # 从 entity_data 中确定主键ID (Determine primary key ID from entity_data)
        # 对于题库内容，entity_id 由 entity_type 前缀后的部分决定
        # (For question bank content, entity_id is determined by the part after entity_type prefix)
        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
            entity_id = entity_type.split(QB_CONTENT_ENTITY_TYPE_PREFIX, 1)[1]
            entity_data["id"] = (
                entity_id  # 确保 'id' 字段在数据中与推断的ID一致 (Ensure 'id' field in data matches inferred ID)
            )
        else:  # 其他通用实体类型 (Other general entity types)
            id_fields = ["id", "uid", "paper_id"]
            found_id = next(
                (
                    str(entity_data[field])
                    for field in id_fields
                    if entity_data.get(field)
                ),
                None,
            )
            if not found_id:
                raise ValueError(
                    "实体数据必须包含可识别的ID字段 (id, uid, paper_id)。 (Entity data must contain a recognizable ID field (id, uid, paper_id).)"
                )
            entity_id = found_id
            # 确保 entity_data 中的主键字段与 entity_id 一致 (Ensure primary key field in entity_data matches entity_id)
            if entity_id != str(
                entity_data.get(entity_id, entity_data.get("id"))
            ):  # 检查常见id字段
                entity_data[id_fields[0]] = (
                    entity_id  # 假设第一个匹配的id_fields是主键字段并同步
                )

        key_name = self._get_entity_key(entity_type, entity_id)
        ids_set_key = self._get_entity_ids_set_key(entity_type)

        if await self.redis.exists(
            key_name
        ):  # 可选：检查实体是否已存在 (Optional: check if entity already exists)
            _redis_repo_logger.warning(
                f"实体键 {key_name} 已存在。将被覆盖。 (Entity key {key_name} already exists. It will be overwritten.)"
            )

        json_string = json.dumps(entity_data)
        async with self.redis.pipeline(
            transaction=True
        ) as pipe:  # 使用Pipeline确保原子性 (Use Pipeline for atomicity)
            await pipe.set(key_name, json_string)
            await pipe.sadd(ids_set_key, entity_id)  # 将ID添加到集合中 (Add ID to set)
            await pipe.execute()
        return entity_data

    async def update(
        self, entity_type: str, entity_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """通过ID在Redis中更新现有实体。(Updates an existing entity by ID in Redis.)"""
        if not self.redis:
            await self.connect()
        assert (
            self.redis is not None
        ), "Redis连接未初始化 (Redis connection not initialized)"

        key_name = self._get_entity_key(entity_type, entity_id)
        current_json_string = await self.redis.get(key_name)
        if not current_json_string:
            return None  # 实体不存在 (Entity does not exist)

        try:
            current_data = json.loads(current_json_string)
        except json.JSONDecodeError:
            _redis_repo_logger.error(
                f"为键 {key_name} 解码现有JSON数据失败（更新操作中）。 (Failed to decode existing JSON for key {key_name} (in update).)"
            )
            return None

        current_data.update(update_data)  # 合并更新 (Merge updates)
        new_json_string = json.dumps(current_data)
        await self.redis.set(
            key_name, new_json_string
        )  # SET会覆盖旧值 (SET overwrites old value)
        return current_data

    async def delete(self, entity_type: str, entity_id: str) -> bool:
        """通过ID从Redis中删除实体及其在ID集合中的引用。(Deletes an entity by ID from Redis and its reference in the ID set.)"""
        if not self.redis:
            await self.connect()
        assert (
            self.redis is not None
        ), "Redis连接未初始化 (Redis connection not initialized)"

        key_name = self._get_entity_key(entity_type, entity_id)
        ids_set_key = self._get_entity_ids_set_key(entity_type)
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.delete(key_name)
            await pipe.srem(
                ids_set_key, entity_id
            )  # 从集合中移除ID (Remove ID from set)
            results = await pipe.execute()
        return (
            results[0] == 1
        )  # DEL命令返回成功删除的键数量 (DEL returns number of keys successfully deleted)

    async def query(
        self,
        entity_type: str,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        在Redis中根据条件查询实体。简单实现：获取所有实体，然后在Python端进行过滤。
        警告：对于大型数据集效率极低。
        (Queries entities in Redis based on conditions. Simple implementation: gets all entities,
         then filters on the Python side. Warning: Extremely inefficient for large datasets.)
        """
        if not self.redis:
            await self.connect()
        assert (
            self.redis is not None
        ), "Redis连接未初始化 (Redis connection not initialized)"
        _redis_repo_logger.warning(
            "正在Redis上执行低效查询（获取所有后过滤）。对于大数据集，请优化。 (Performing inefficient query on Redis (get all then filter). Please optimize for large datasets.)"
        )

        all_ids_key = self._get_entity_ids_set_key(entity_type)
        all_entity_ids = list(await self.redis.smembers(all_ids_key))
        try:
            all_entity_ids.sort()
        except TypeError:
            _redis_repo_logger.warning(
                f"无法为实体类型 '{entity_type}' 的ID排序（查询中），结果可能不一致。 (Cannot sort IDs for entity type '{entity_type}' (in query), results may be inconsistent.)"
            )

        if not all_entity_ids:
            return []

        # 分批获取以避免Redis MGET命令过长或响应过大 (Fetch in batches to avoid overly long MGET or large responses)
        # 这是一个简单的优化，更复杂的场景可能需要更智能的分批策略
        # (This is a simple optimization; more complex scenarios might need smarter batching)
        batch_size = 500  # 可配置的批处理大小 (Configurable batch size)
        matched_entities: List[Dict[str, Any]] = []

        all_fetched_entities: List[Dict[str, Any]] = []
        for i in range(0, len(all_entity_ids), batch_size):
            batch_ids = all_entity_ids[i : i + batch_size]
            keys_to_fetch = [
                self._get_entity_key(entity_type, eid) for eid in batch_ids
            ]
            if not keys_to_fetch:
                continue

            json_strings = await self.redis.mget(*keys_to_fetch)
            for idx, json_string in enumerate(json_strings):
                if json_string:
                    try:
                        all_fetched_entities.append(json.loads(json_string))
                    except json.JSONDecodeError:
                        _redis_repo_logger.error(
                            f"为键 {keys_to_fetch[idx]} 解码JSON失败（查询中）。 (Failed to decode JSON for key {keys_to_fetch[idx]} (in query).)"
                        )
                else:
                    _redis_repo_logger.warning(
                        f"键 {keys_to_fetch[idx]} 的数据在MGET查询中缺失。 (Data for key {keys_to_fetch[idx]} missing in MGET query.)"
                    )

        # 在Python端应用过滤条件 (Apply filter conditions on Python side)
        for entity in all_fetched_entities:
            match = all(
                entity.get(key) == value for key, value in conditions.items()
            )  # 精确匹配 (Exact match)
            if match:
                matched_entities.append(entity)

        return matched_entities[
            skip : skip + limit
        ]  # 对过滤后的结果应用分页 (Apply pagination to filtered results)

    async def get_all_entity_types(self) -> List[str]:
        """
        尝试通过扫描 `entity_ids:*` 模式的键来动态发现所有实体类型。
        (Attempts to dynamically discover all entity types by scanning keys matching `entity_ids:*` pattern.)
        """
        if not self.redis:
            await self.connect()
        assert (
            self.redis is not None
        ), "Redis连接未初始化 (Redis connection not initialized)"

        cursor = b"0"  # aioredis scan cursor starts as bytes
        found_types = set()
        prefix_to_scan = f"{ENTITY_IDS_SET_KEY_PREFIX}:*"
        while cursor:  # Loop until cursor becomes 0 (or None for some clients)
            cursor, keys = await self.redis.scan(
                cursor=cursor, match=prefix_to_scan, count=100
            )
            for (
                key_str
            ) in (
                keys
            ):  # Keys are already decoded if decode_responses=True for Redis client
                entity_type = key_str.split(":", 1)[
                    1
                ]  # 提取 "entity_ids:" 之后的部分 (Extract part after "entity_ids:")
                found_types.add(entity_type)
            if cursor == b"0":  # End of scan
                break

        if not found_types:
            _redis_repo_logger.warning(
                "get_all_entity_types: 未找到实体ID集合。返回预定义列表或空列表。 (No entity ID sets found. Returning predefined list or empty list.)"
            )
            return [
                "user",
                "paper",
                "question_bank_metadata",
                QB_CONTENT_ENTITY_TYPE_PREFIX[:-1],
            ]  # 提供一些默认类型 (Provide some default types)
        return list(found_types)

    async def persist_all_data(self) -> None:
        """对于Redis，数据实时持久化（取决于Redis配置），此方法为空操作。(For Redis, data is persisted live (depending on Redis config); this is a no-op.)"""
        _redis_repo_logger.info(
            "RedisStorageRepository: 'persist_all_data' 被调用 (空操作，Redis实时持久化)。 (Called (no-op, Redis persists live).)"
        )
        pass


__all__ = [
    "RedisStorageRepository"  # 导出Redis存储库类 (Export Redis repository class)
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了Redis数据存储库的实现。
    # (This module should not be executed as the main script. It defines the Redis data storage repository implementation.)
    _redis_repo_logger.info(f"模块 {__name__} 定义了Redis存储库，不应直接执行。")
    print(
        f"模块 {__name__} 定义了Redis存储库，不应直接执行。 (This module defines the Redis repository and should not be executed directly.)"
    )
