# -*- coding: utf-8 -*-
"""
PostgreSQL 数据存储库实现模块。
(PostgreSQL Data Storage Repository Implementation Module.)

该模块提供了 `IDataStorageRepository` 接口的一个具体实现，
使用 PostgreSQL 作为后端数据库。它利用 `asyncpg` 库进行异步数据库操作。
(This module provides a concrete implementation of the `IDataStorageRepository` interface,
using PostgreSQL as the backend database. It utilizes the `asyncpg` library
for asynchronous database operations.)
"""

import logging
import uuid  # 用于处理UUID类型 (For handling UUID type)
from typing import Any, Dict, List, Optional, Union

import asyncpg  # type: ignore # (asyncpg 默认可能没有类型存根 / asyncpg might not have stubs by default)

from app.core.interfaces import (
    IDataStorageRepository,
)  # 导入抽象基类 (Import abstract base class)

# QB_CONTENT_ENTITY_TYPE_PREFIX 用于动态识别题库内容实体类型，
# 其实际值应与 qb_crud.py 中定义的一致，或通过配置传入。
# (QB_CONTENT_ENTITY_TYPE_PREFIX is used for dynamically identifying question bank content entity types.
#  Its actual value should be consistent with the definition in qb_crud.py or passed via configuration.)
from .qb_crud import QB_CONTENT_ENTITY_TYPE_PREFIX

_postgres_repo_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例


def _record_to_dict(record: Optional[asyncpg.Record]) -> Optional[Dict[str, Any]]:
    """
    辅助函数：将单个 asyncpg.Record 对象转换为字典。
    如果记录为 None，则返回 None。
    (Helper function: Converts a single asyncpg.Record object to a dictionary.
    Returns None if the record is None.)
    """
    if record:
        return dict(record)  # asyncpg.Record 对象可以直接转换为字典
    return None


def _records_to_list_of_dicts(records: List[asyncpg.Record]) -> List[Dict[str, Any]]:
    """
    辅助函数：将 asyncpg.Record 对象列表转换为字典列表。
    (Helper function: Converts a list of asyncpg.Record objects to a list of dictionaries.)
    """
    return [dict(record) for record in records]


class PostgresStorageRepository(IDataStorageRepository):
    """
    使用 PostgreSQL 进行持久化的数据存储库实现。
    此类实现了 IDataStorageRepository 接口中定义的所有异步方法，
    并与 PostgreSQL 数据库进行交互。
    (A data storage repository implementation using PostgreSQL for persistence.
    This class implements all asynchronous methods defined in the IDataStorageRepository interface
    and interacts with a PostgreSQL database.)
    """

    def __init__(
        self,
        dsn: Optional[str] = None,  # PostgreSQL DSN (Data Source Name)
        host: Optional[str] = None,  # 数据库服务器主机名或IP (DB server hostname or IP)
        port: Optional[Union[int, str]] = None,  # 数据库服务器端口 (DB server port)
        user: Optional[str] = None,  # 连接用户名 (Connection username)
        password: Optional[str] = None,  # 连接密码 (Connection password)
        database: Optional[str] = None,  # 连接的数据库名 (Database name to connect to)
    ):
        """
        初始化 PostgresStorageRepository。
        可以通过DSN字符串或单独的连接参数（主机、用户、数据库等）来配置连接。
        (Initializes the PostgresStorageRepository.
        Connection can be configured via a DSN string or individual connection parameters
        (host, user, database, etc.).)

        参数 (Args):
            dsn (Optional[str]): PostgreSQL DSN。如果提供，则优先使用。
                                 (PostgreSQL DSN. If provided, it takes precedence.)
            host (Optional[str]): 数据库服务器主机名或IP地址。
            port (Optional[Union[int, str]]): 数据库服务器端口。
            user (Optional[str]): 用于数据库连接的用户名。
            password (Optional[str]): 用于数据库连接的密码。
            database (Optional[str]): 要连接的数据库名称。

        异常 (Raises):
            ValueError: 如果既未提供 DSN 也未提供足够的单独连接参数。
                        (If neither DSN nor sufficient individual connection parameters are provided.)
        """
        if not dsn and not (host and user and database):
            raise ValueError(
                "必须提供DSN或(主机、用户、数据库名)以建立PostgreSQL连接。 (DSN or (host, user, database name) must be provided for PostgreSQL connection.)"
            )

        self.dsn = dsn
        self.conn_params: Dict[str, Any] = {
            "host": host,
            "port": int(port) if port else None,
            "user": user,
            "password": password,
            "database": database,
        }
        if not self.dsn:  # 如果不使用DSN，则过滤掉值为None的参数 (If not using DSN, filter out None parameters)
            self.conn_params = {
                k: v for k, v in self.conn_params.items() if v is not None
            }

        self.pool: Optional[asyncpg.Pool] = (
            None  # asyncpg 连接池实例 (asyncpg connection pool instance)
        )
        _postgres_repo_logger.info(
            "PostgresStorageRepository 已初始化。 (PostgresStorageRepository initialized.)"
        )

    async def connect(self) -> None:
        """
        建立与 PostgreSQL 数据库的连接池。
        如果连接池已存在，则此操作为空操作。
        如果连接失败，会记录错误并可能抛出异常。
        (Establishes a connection pool to the PostgreSQL database.
        If the pool already exists, this is a no-op.
        If connection fails, logs an error and may raise an exception.)
        """
        if self.pool:
            _postgres_repo_logger.info(
                "PostgreSQL 连接池已存在。 (PostgreSQL connection pool already exists.)"
            )
            return
        try:
            if self.dsn:
                self.pool = await asyncpg.create_pool(
                    dsn=self.dsn, min_size=1, max_size=10
                )  # 配置连接池大小 (Configure pool size)
            else:
                self.pool = await asyncpg.create_pool(
                    **self.conn_params, min_size=1, max_size=10
                )
            _postgres_repo_logger.info(
                "PostgreSQL 连接池已成功建立。 (PostgreSQL connection pool established successfully.)"
            )
        except Exception as e:
            _postgres_repo_logger.error(
                f"建立 PostgreSQL 连接池失败 (Failed to establish PostgreSQL connection pool): {e}",
                exc_info=True,
            )
            raise

    async def disconnect(self) -> None:
        """关闭 PostgreSQL 连接池。(Closes the PostgreSQL connection pool.)"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            _postgres_repo_logger.info(
                "PostgreSQL 连接池已关闭。 (PostgreSQL connection pool closed.)"
            )
        else:
            _postgres_repo_logger.info(
                "无活动的 PostgreSQL 连接池可关闭。 (No active PostgreSQL connection pool to close.)"
            )

    async def init_storage_if_needed(
        self,
        entity_type: str,
        default_data: Optional[Any] = None,  # default_data 在此实现中未使用
    ) -> None:
        """
        确保指定实体类型的数据库表存在。如果不存在，则创建它。
        `default_data` 参数在此 PostgreSQL 实现中通常不直接使用。
        (Ensures the database table for the specified entity type exists. Creates it if it doesn't.
        The `default_data` parameter is typically not used directly in this PostgreSQL implementation.)

        参数 (Args):
            entity_type (str): 需要初始化存储的实体类型。(Entity type for which storage needs to be initialized.)
            default_data (Optional[Any]): (未使用) 用于填充的默认数据。((Unused) Default data for population.)
        """
        if not self.pool:
            _postgres_repo_logger.warning(
                "连接池未初始化，尝试在 init_storage_if_needed 中连接。 (Connection pool not initialized, attempting to connect in init_storage_if_needed.)"
            )
            await self.connect()
        assert self.pool is not None, (
            "数据库连接池在init_storage_if_needed时必须可用。 (DB pool must be available.)"
        )

        async with (
            self.pool.acquire() as conn
        ):  # 从连接池获取一个连接 (Acquire a connection from the pool)
            # 根据实体类型定义表结构并创建 (Define and create table structure based on entity type)
            if entity_type == "user":  # 用户表
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        uid TEXT PRIMARY KEY, nickname TEXT, email TEXT, qq TEXT,
                        tags JSONB, hashed_password TEXT
                    )"""
                )
                _postgres_repo_logger.info(
                    "表 'users' 已检查/创建。 (Table 'users' checked/created.)"
                )
            elif entity_type == "paper":  # 试卷表
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS papers (
                        paper_id UUID PRIMARY KEY,
                        user_uid TEXT,
                        creation_time_utc TIMESTAMPTZ,
                        creation_ip TEXT,
                        difficulty TEXT,
                        paper_questions JSONB,
                        score INTEGER,
                        submitted_answers_card JSONB,
                        submission_time_utc TIMESTAMPTZ,
                        submission_ip TEXT,
                        pass_status TEXT,
                        passcode TEXT,
                        last_update_time_utc TIMESTAMPTZ,
                        last_update_ip TEXT,
                        subjective_questions_count INTEGER DEFAULT 0,
                        graded_subjective_questions_count INTEGER DEFAULT 0,
                        pending_manual_grading_count INTEGER DEFAULT 0,
                        total_score REAL DEFAULT 0.0
                    )"""
                )
                _postgres_repo_logger.info(
                    "表 'papers' 已检查/创建。 (Table 'papers' checked/created.)"
                )
            elif entity_type == "question_bank_metadata":  # 题库元数据表
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS question_bank_metadata (
                        id TEXT PRIMARY KEY, name TEXT, description TEXT,
                        default_questions INTEGER, total_questions INTEGER
                    )"""
                )
                _postgres_repo_logger.info(
                    "表 'question_bank_metadata' 已检查/创建。 (Table 'question_bank_metadata' checked/created.)"
                )
            elif entity_type == "question_bank_contents" or entity_type.startswith(
                QB_CONTENT_ENTITY_TYPE_PREFIX
            ):  # 题库内容表
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS question_bank_contents (
                        difficulty_id TEXT, content_id TEXT, questions JSONB,
                        PRIMARY KEY (difficulty_id, content_id)
                    )"""
                )
                _postgres_repo_logger.info(
                    "表 'question_bank_contents' 已检查/创建。 (Table 'question_bank_contents' checked/created.)"
                )
            else:
                _postgres_repo_logger.warning(
                    f"实体类型 '{entity_type}' 的表结构定义未找到。 (Table structure definition for entity type '{entity_type}' not found.)"
                )

    def _get_table_info(self, entity_type: str) -> tuple[str, str]:
        """
        辅助方法：根据实体类型获取对应的表名和主键列名。
        (Helper method: Gets the corresponding table name and primary key column name based on entity type.)
        """
        if entity_type == "user":
            return "users", "uid"
        elif entity_type == "paper":
            return "papers", "paper_id"
        elif entity_type == "question_bank_metadata":
            return "question_bank_metadata", "id"
        elif entity_type == "question_bank_contents" or entity_type.startswith(
            QB_CONTENT_ENTITY_TYPE_PREFIX
        ):
            return (
                "question_bank_contents",
                "difficulty_id",
            )  # 'difficulty_id' is part of composite PK
        else:
            _postgres_repo_logger.error(
                f"未知的实体类型，无法映射到表名 (Unknown entity type, cannot map to table name): {entity_type}"
            )
            raise ValueError(
                f"不支持的实体类型 (Unsupported entity type): {entity_type}"
            )

    async def get_by_id(
        self, entity_type: str, entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """通过ID从PostgreSQL数据库中检索单个实体。(Retrieves a single entity by ID from PostgreSQL.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None

        table_name, id_column = self._get_table_info(entity_type)
        query_params: list[Any] = []
        query: str

        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):  # 题库内容特殊处理
            query = f"SELECT questions FROM {table_name} WHERE difficulty_id = $1 AND content_id = $2"
            query_params = [entity_id, "default"]  # 假设 content_id 为 'default'
        elif table_name == "papers" and id_column == "paper_id":  # Paper ID 是 UUID
            try:
                query_params = [uuid.UUID(entity_id)]
                query = f"SELECT * FROM {table_name} WHERE {id_column} = $1"
            except ValueError:
                _postgres_repo_logger.error(
                    f"无效的UUID格式作为 paper_id (Invalid UUID format for paper_id): {entity_id}"
                )
                return None
        else:
            query_params = [entity_id]
            query = f"SELECT * FROM {table_name} WHERE {id_column} = $1"

        async with self.pool.acquire() as conn:
            try:
                record = await conn.fetchrow(query, *query_params)
                if (
                    entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX) and record
                ):  # 返回题库内容特定结构
                    return (
                        {"id": entity_id, "questions": record["questions"]}
                        if record
                        else None
                    )
                return _record_to_dict(record)
            except asyncpg.exceptions.UndefinedTableError:  # 表不存在的处理
                _postgres_repo_logger.warning(
                    f"表 '{table_name}' 不存在 (get_by_id)。尝试初始化... (Table '{table_name}' does not exist (get_by_id). Attempting to initialize...)"
                )
                await self.init_storage_if_needed(entity_type)
                return None  # 初始化后，当前查询仍返回None
            except Exception as e:
                _postgres_repo_logger.error(
                    f"执行 get_by_id (实体类型 (Entity Type): {entity_type}, ID: {entity_id}) 时出错 (Error): {e}",
                    exc_info=True,
                )
                return None

    async def get_all(
        self, entity_type: str, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """从PostgreSQL数据库检索指定类型的所有实体，支持分页。(Retrieves all entities of a specified type from PostgreSQL, with pagination.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None

        table_name, id_column = self._get_table_info(entity_type)
        order_by_clause = f"ORDER BY {id_column}" if id_column else "ORDER BY 1"
        query = f"SELECT * FROM {table_name} {order_by_clause} OFFSET $1 LIMIT $2"

        async with self.pool.acquire() as conn:
            try:
                records = await conn.fetch(query, skip, limit)
                return _records_to_list_of_dicts(records)
            except asyncpg.exceptions.UndefinedTableError:
                _postgres_repo_logger.warning(
                    f"表 '{table_name}' 不存在 (get_all)。尝试初始化... (Table '{table_name}' does not exist (get_all). Attempting to initialize...)"
                )
                await self.init_storage_if_needed(entity_type)
                return []  # 初始化后，当前查询返回空列表
            except Exception as e:
                _postgres_repo_logger.error(
                    f"执行 get_all (实体类型 (Entity Type): {entity_type}) 时出错 (Error): {e}",
                    exc_info=True,
                )
                return []

    async def create(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """在PostgreSQL数据库中创建一个新实体。(Creates a new entity in PostgreSQL.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None

        table_name, _ = self._get_table_info(entity_type)
        db_data = entity_data.copy()

        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):  # 题库内容特殊处理
            difficulty_id_from_type = entity_type.split(
                QB_CONTENT_ENTITY_TYPE_PREFIX, 1
            )[1]
            db_data["difficulty_id"] = entity_data.get(
                "id", difficulty_id_from_type
            )  # 'id' in entity_data is difficulty_id
            db_data.pop("id", None)  # 移除原始 'id' 键，因为它现在是 difficulty_id
            db_data["content_id"] = entity_data.get(
                "content_id", "default"
            )  # 默认 content_id
        elif (
            table_name == "papers"
            and "paper_id" in db_data
            and isinstance(db_data["paper_id"], str)
        ):
            try:
                db_data["paper_id"] = uuid.UUID(db_data["paper_id"])  # 转换为UUID类型
            except ValueError as e:
                raise ValueError(
                    f"无效的UUID格式作为 paper_id (创建时) (Invalid UUID for paper_id (on create)): {db_data['paper_id']}"
                ) from e

        columns = ", ".join(db_data.keys())
        placeholders = ", ".join([f"${i + 1}" for i in range(len(db_data))])
        values = list(db_data.values())
        query = (
            f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) RETURNING *"
        )

        async with self.pool.acquire() as conn:
            try:
                inserted_record = await conn.fetchrow(query, *values)
                if not inserted_record:
                    raise ValueError(
                        "插入操作未返回新记录。(Insert operation did not return a new record.)"
                    )
                if entity_type.startswith(
                    QB_CONTENT_ENTITY_TYPE_PREFIX
                ):  # 返回题库内容特定结构
                    return {
                        "id": inserted_record["difficulty_id"],
                        "questions": inserted_record["questions"],
                    }
                return _record_to_dict(inserted_record)  # type: ignore
            except asyncpg.exceptions.UniqueViolationError as e:  # 主键冲突
                pk_val = entity_data.get(
                    self._get_table_info(entity_type)[1], "未知ID (Unknown ID)"
                )
                _postgres_repo_logger.error(
                    f"创建实体 (类型 (Type): {entity_type}, ID: {pk_val}) 时发生唯一约束冲突 (UniqueViolationError): {e}",
                    exc_info=True,
                )
                raise ValueError(
                    f"实体类型 '{entity_type}' 中具有此ID的实体已存在。 (Entity with this ID already exists in type '{entity_type}'.)"
                ) from e
            except asyncpg.exceptions.UndefinedTableError:  # 表不存在
                _postgres_repo_logger.warning(
                    f"表 '{table_name}' 不存在 (create)。尝试初始化... (Table '{table_name}' does not exist (create). Attempting to initialize...)"
                )
                await self.init_storage_if_needed(entity_type)
                inserted_record = await conn.fetchrow(query, *values)  # 重试插入
                if not inserted_record:
                    raise ValueError(
                        "插入操作在表创建尝试后仍然失败。(Insert failed after table creation attempt.)"
                    ) from None
                if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
                    return {
                        "id": inserted_record["difficulty_id"],
                        "questions": inserted_record["questions"],
                    }
                return _record_to_dict(inserted_record)  # type: ignore
            except Exception as e:
                _postgres_repo_logger.error(
                    f"执行 create (实体类型 (Entity Type): {entity_type}) 时出错 (Error): {e}",
                    exc_info=True,
                )
                raise

    async def update(
        self, entity_type: str, entity_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """通过ID在PostgreSQL数据库中更新现有实体。(Updates an existing entity by ID in PostgreSQL.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None

        table_name, id_column = self._get_table_info(entity_type)
        data_to_set = update_data.copy()
        if not data_to_set:
            return await self.get_by_id(entity_type, entity_id)

        if (
            table_name == "papers"
            and "paper_id" in data_to_set
            and isinstance(data_to_set["paper_id"], str)
        ):
            try:
                data_to_set["paper_id"] = uuid.UUID(data_to_set["paper_id"])
            except ValueError:
                _postgres_repo_logger.error(
                    f"更新操作中 paper_id 格式无效 (Invalid paper_id format in update): {data_to_set['paper_id']}"
                )
                data_to_set.pop("paper_id")

        set_clause_parts: List[str] = []
        values: List[Any] = []
        param_idx = 1
        for key, value in data_to_set.items():
            set_clause_parts.append(f"{key} = ${param_idx}")
            values.append(value)
            param_idx += 1
        set_clause = ", ".join(set_clause_parts)
        query_params: List[Any] = values
        query: str

        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):  # 题库内容更新
            content_id_val = update_data.get("content_id", "default")
            query = f"UPDATE {table_name} SET {set_clause} WHERE difficulty_id = ${param_idx} AND content_id = ${param_idx + 1} RETURNING *"
            query_params.extend([entity_id, content_id_val])
        elif table_name == "papers" and id_column == "paper_id":  # Paper UUID 处理
            try:
                query_params.append(uuid.UUID(entity_id))
                query = f"UPDATE {table_name} SET {set_clause} WHERE {id_column} = ${param_idx} RETURNING *"
            except ValueError:
                _postgres_repo_logger.error(
                    f"更新操作中 entity_id (paper_id) 格式无效 (Invalid entity_id (paper_id) format in update): {entity_id}"
                )
                return None
        else:  # 其他实体
            query_params.append(entity_id)
            query = f"UPDATE {table_name} SET {set_clause} WHERE {id_column} = ${param_idx} RETURNING *"

        async with self.pool.acquire() as conn:
            try:
                updated_record = await conn.fetchrow(query, *query_params)
                if (
                    entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX)
                    and updated_record
                ):
                    return {
                        "id": updated_record["difficulty_id"],
                        "questions": updated_record["questions"],
                    }
                return _record_to_dict(updated_record)
            except asyncpg.exceptions.UndefinedTableError:
                _postgres_repo_logger.warning(
                    f"表 '{table_name}' 不存在 (update)。尝试初始化... (Table '{table_name}' does not exist (update). Attempting to initialize...)"
                )
                await self.init_storage_if_needed(entity_type)
                return None
            except Exception as e:
                _postgres_repo_logger.error(
                    f"执行 update (实体类型 (Entity Type): {entity_type}, ID: {entity_id}) 时出错 (Error): {e}",
                    exc_info=True,
                )
                return None

    async def delete(self, entity_type: str, entity_id: str) -> bool:
        """通过ID从PostgreSQL数据库中删除实体。(Deletes an entity by ID from PostgreSQL.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None

        table_name, id_column = self._get_table_info(entity_type)
        query_params: List[Any] = []
        query: str

        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):  # 题库内容删除
            query = (
                f"DELETE FROM {table_name} WHERE difficulty_id = $1 AND content_id = $2"
            )
            query_params = [entity_id, "default"]
        elif table_name == "papers" and id_column == "paper_id":  # Paper UUID 处理
            try:
                query_params = [uuid.UUID(entity_id)]
                query = f"DELETE FROM {table_name} WHERE {id_column} = $1"
            except ValueError:
                _postgres_repo_logger.error(
                    f"删除操作中 entity_id (paper_id) 格式无效 (Invalid entity_id (paper_id) format in delete): {entity_id}"
                )
                return False
        else:  # 其他实体
            query_params = [entity_id]
            query = f"DELETE FROM {table_name} WHERE {id_column} = $1"

        async with self.pool.acquire() as conn:
            try:
                result_status_str = await conn.execute(query, *query_params)
                return (
                    result_status_str.startswith("DELETE")
                    and int(result_status_str.split(" ")[1]) > 0
                )
            except asyncpg.exceptions.UndefinedTableError:
                _postgres_repo_logger.warning(
                    f"表 '{table_name}' 不存在 (delete)。尝试初始化... (Table '{table_name}' does not exist (delete). Attempting to initialize...)"
                )
                await self.init_storage_if_needed(entity_type)
                return False
            except Exception as e:
                _postgres_repo_logger.error(
                    f"执行 delete (实体类型 (Entity Type): {entity_type}, ID: {entity_id}) 时出错 (Error): {e}",
                    exc_info=True,
                )
                return False

    async def query(
        self,
        entity_type: str,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """根据一组条件从PostgreSQL数据库查询实体。(Queries entities from PostgreSQL based on a set of conditions.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None

        table_name, id_column = self._get_table_info(entity_type)
        order_by_clause = f"ORDER BY {id_column}" if id_column else "ORDER BY 1"
        where_clauses: List[str] = []
        values: List[Any] = []
        param_idx = 1
        for key, value in conditions.items():
            where_clauses.append(
                f"{key} = ${param_idx}"
            )  # PostgreSQL 使用 $1, $2...作为占位符
            values.append(value)
            param_idx += 1
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        values.extend([skip, limit])
        query = f"SELECT * FROM {table_name} WHERE {where_sql} {order_by_clause} OFFSET ${param_idx} LIMIT ${param_idx + 1}"

        async with self.pool.acquire() as conn:
            try:
                records = await conn.fetch(query, *values)
                if entity_type.startswith(
                    QB_CONTENT_ENTITY_TYPE_PREFIX
                ):  # 返回题库内容特定结构
                    return [
                        {"id": r["difficulty_id"], "questions": r["questions"]}
                        for r in records
                    ]
                return _records_to_list_of_dicts(records)
            except asyncpg.exceptions.UndefinedTableError:
                _postgres_repo_logger.warning(
                    f"表 '{table_name}' 不存在 (query)。尝试初始化... (Table '{table_name}' does not exist (query). Attempting to initialize...)"
                )
                await self.init_storage_if_needed(entity_type)
                return []
            except Exception as e:
                _postgres_repo_logger.error(
                    f"执行 query (实体类型 (Entity Type): {entity_type}, 条件 (Conditions): {conditions}) 时出错 (Error): {e}",
                    exc_info=True,
                )
                return []

    async def get_all_entity_types(self) -> List[str]:
        """返回此存储库已知或预期管理的所有实体类型的列表。(Returns a list of all entity types known/expected to be managed.)"""
        _postgres_repo_logger.warning(
            "get_all_entity_types 对于PostgreSQL未完全实现动态发现，返回已知类型列表。 (get_all_entity_types not fully dynamic for PostgreSQL, returns known types.)"
        )
        return [
            "user",
            "paper",
            "question_bank_metadata",
            "question_bank_contents",
            QB_CONTENT_ENTITY_TYPE_PREFIX + "*",
        ]  # 使用通配符表示动态题库内容

    async def persist_all_data(self) -> None:
        """对于PostgreSQL，数据实时持久化，此方法为空操作。(For PostgreSQL, data is persisted live; this is a no-op.)"""
        _postgres_repo_logger.info(
            "PostgresStorageRepository: 'persist_all_data' 被调用 (空操作，数据实时持久化)。 (Called (no-op, data is persisted live).)"
        )
        pass


__all__ = [
    "PostgresStorageRepository"  # 导出PostgreSQL存储库类 (Export PostgreSQL repository class)
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了PostgreSQL数据存储库的实现。
    # (This module should not be executed as the main script. It defines the PostgreSQL data storage repository implementation.)
    _postgres_repo_logger.info(
        f"模块 {__name__} 定义了PostgreSQL存储库，不应直接执行。"
    )
    print(
        f"模块 {__name__} 定义了PostgreSQL存储库，不应直接执行。 (This module defines the PostgreSQL repository and should not be executed directly.)"
    )
