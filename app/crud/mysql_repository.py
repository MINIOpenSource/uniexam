# -*- coding: utf-8 -*-
"""
MySQL/MariaDB 数据存储库实现模块。
(MySQL/MariaDB Data Storage Repository Implementation Module.)

该模块提供了 `IDataStorageRepository` 接口的一个具体实现，
使用 MySQL 或 MariaDB 作为后端数据库。它利用 `aiomysql` 库进行异步数据库操作。
(This module provides a concrete implementation of the `IDataStorageRepository` interface,
using MySQL or MariaDB as the backend database. It utilizes the `aiomysql` library
for asynchronous database operations.)
"""

import asyncio
import json  # 用于序列化/反序列化JSON字段 (For serializing/deserializing JSON fields)
import logging
from typing import Any, Dict, List, Optional

import aiomysql  # type: ignore # aiomysql 可能没有完整的类型存根 (aiomysql might not have complete type stubs)
from pymysql.err import (
    IntegrityError,
    OperationalError,
)  # 用于特定的MySQL错误处理 (For specific MySQL error handling)

from app.core.interfaces import (
    IDataStorageRepository,
)  # 导入抽象基类 (Import abstract base class)

_mysql_repo_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例

# 表名常量 (Table name constants)
USER_TABLE = "users"  # 用户表 (Users table)
PAPER_TABLE = "papers"  # 试卷表 (Papers table)
QB_METADATA_TABLE = (
    "question_bank_metadata"  # 题库元数据表 (Question bank metadata table)
)
QB_CONTENT_TABLE = "question_bank_contents"  # 题库内容表 (Question bank contents table)
# 注意: QB_CONTENT_ENTITY_TYPE_PREFIX 用于动态识别题库内容实体类型，
# 其实际值应与 qb_crud.py 中定义的一致，或通过配置传入。
# (Note: QB_CONTENT_ENTITY_TYPE_PREFIX is used for dynamically identifying question bank content entity types.
#  Its actual value should be consistent with the definition in qb_crud.py or passed via configuration.)
QB_CONTENT_ENTITY_TYPE_PREFIX = "qb_content_"


class MySQLStorageRepository(IDataStorageRepository):
    """
    一个使用 MySQL/MariaDB 进行持久化的数据存储库实现。
    此类实现了 IDataStorageRepository 接口中定义的所有异步方法。
    (A data storage repository implementation using MySQL/MariaDB for persistence.
    This class implements all asynchronous methods defined in the IDataStorageRepository interface.)
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        db: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        """
        初始化 MySQLStorageRepository。
        (Initializes the MySQLStorageRepository.)

        参数 (Args):
            host (str): 数据库服务器主机名或IP地址。(Database server hostname or IP address.)
            port (int): 数据库服务器端口。(Database server port.)
            user (str): 用于数据库连接的用户名。(Username for database connection.)
            password (str): 用于数据库连接的密码。(Password for database connection.)
            db (str): 要连接的数据库名称。(Name of the database to connect to.)
            loop (Optional[asyncio.AbstractEventLoop]): (可选) asyncio 事件循环。如果未提供，则使用默认循环。
                                                       ((Optional) asyncio event loop. Uses default loop if not provided.)
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.db = db
        self.loop = loop or asyncio.get_event_loop()  # 获取当前或指定的事件循环
        self.pool: Optional[aiomysql.Pool] = (
            None  # aiomysql 连接池实例 (aiomysql connection pool instance)
        )
        _mysql_repo_logger.info(
            "MySQLStorageRepository 已初始化。 (MySQLStorageRepository initialized.)"
        )

    async def connect(self) -> None:
        """建立与 MySQL 数据库的连接池。(Establishes a connection pool to the MySQL database.)"""
        if self.pool:
            _mysql_repo_logger.info(
                "MySQL 连接池已存在。 (MySQL connection pool already exists.)"
            )
            return
        try:
            self.pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.db,
                loop=self.loop,
                autocommit=True,  # 简化事务管理，每个语句自动提交 (Simplify transaction management, auto-commit each statement)
            )
            _mysql_repo_logger.info(
                "MySQL 连接池已成功建立。 (MySQL connection pool established successfully.)"
            )
        except OperationalError as e:
            _mysql_repo_logger.error(
                f"建立 MySQL 连接池失败 (Failed to establish MySQL connection pool): {e}",
                exc_info=True,
            )
            raise

    async def disconnect(self) -> None:
        """关闭 MySQL 连接池。(Closes the MySQL connection pool.)"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()  # 等待所有连接关闭 (Wait for all connections to close)
            self.pool = None
            _mysql_repo_logger.info(
                "MySQL 连接池已关闭。 (MySQL connection pool closed.)"
            )
        else:
            _mysql_repo_logger.info(
                "无活动的 MySQL 连接池可关闭。 (No active MySQL connection pool to close.)"
            )

    async def init_storage_if_needed(
        self,
        entity_type: str,
        default_data: Optional[Any] = None,  # default_data 在此实现中未使用
    ) -> None:
        """
        确保指定实体类型的数据库表存在。如果不存在，则创建它。
        (Ensures the database table for the specified entity type exists. Creates it if it doesn't.)
        `default_data` 参数在此 MySQL 实现中通常不直接使用来填充表，因为表结构是预定义的，
        而初始数据填充（如管理员用户）通常由相应的CRUD逻辑在应用启动时处理。
        ((The `default_data` parameter is typically not used directly in this MySQL implementation
         to populate tables, as table structures are predefined, and initial data population
         (like an admin user) is usually handled by corresponding CRUD logic at application startup.))

        参数 (Args):
            entity_type (str): 需要初始化存储的实体类型。(Entity type for which storage needs to be initialized.)
            default_data (Optional[Any]): (未使用) 用于填充的默认数据。((Unused) Default data for population.)
        """
        if not self.pool:
            _mysql_repo_logger.warning(
                "连接池未初始化，尝试在 init_storage_if_needed 中连接。 (Connection pool not initialized, attempting to connect in init_storage_if_needed.)"
            )
            await self.connect()
        assert (
            self.pool is not None
        ), "数据库连接池在init_storage_if_needed时必须可用。 (Database connection pool must be available in init_storage_if_needed.)"

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # MySQL的TEXT类型通常足够大，JSON类型用于存储JSON文档。CHAR(36)用于UUID。DATETIME用于时间戳。
                # (MySQL's TEXT type is usually large enough; JSON type for JSON documents. CHAR(36) for UUIDs. DATETIME for timestamps.)
                if entity_type == "user":  # 用户表结构
                    await cur.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {USER_TABLE} (
                            uid VARCHAR(255) PRIMARY KEY,
                            nickname TEXT,
                            email TEXT,
                            qq TEXT,
                            tags JSON,
                            hashed_password TEXT
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                        """
                    )
                    _mysql_repo_logger.info(
                        f"表 '{USER_TABLE}' 已检查/创建。 (Table '{USER_TABLE}' checked/created.)"
                    )
                elif entity_type == "paper":  # 试卷表结构
                    await cur.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {PAPER_TABLE} (
                            paper_id CHAR(36) PRIMARY KEY,
                            user_uid TEXT,
                            creation_time_utc DATETIME,
                            creation_ip TEXT,
                            difficulty TEXT,
                            paper_questions JSON,
                            score INTEGER,
                            submitted_answers_card JSON,
                            submission_time_utc DATETIME,
                            submission_ip TEXT,
                            pass_status TEXT,
                            passcode TEXT,
                            last_update_time_utc DATETIME,
                            last_update_ip TEXT,
                            subjective_questions_count INT DEFAULT 0,
                            graded_subjective_questions_count INT DEFAULT 0,
                            pending_manual_grading_count INT DEFAULT 0,
                            total_score FLOAT DEFAULT 0.0
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                        """
                    )
                    _mysql_repo_logger.info(
                        f"表 '{PAPER_TABLE}' 已检查/创建。 (Table '{PAPER_TABLE}' checked/created.)"
                    )
                elif entity_type == "question_bank_metadata":  # 题库元数据表结构
                    await cur.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {QB_METADATA_TABLE} (
                            id VARCHAR(255) PRIMARY KEY,
                            name TEXT,
                            description TEXT,
                            default_questions INTEGER,
                            total_questions INTEGER
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                        """
                    )
                    _mysql_repo_logger.info(
                        f"表 '{QB_METADATA_TABLE}' 已检查/创建。 (Table '{QB_METADATA_TABLE}' checked/created.)"
                    )
                elif entity_type == "question_bank_contents" or entity_type.startswith(
                    QB_CONTENT_ENTITY_TYPE_PREFIX
                ):  # 题库内容表结构
                    await cur.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {QB_CONTENT_TABLE} (
                            difficulty_id VARCHAR(255),
                            content_id VARCHAR(255), /* 用于区分同一难度的不同内容版本或部分，默认为 "default" */
                            questions JSON, /* 存储题目列表的JSON数组 */
                            PRIMARY KEY (difficulty_id, content_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                        """
                    )
                    _mysql_repo_logger.info(
                        f"表 '{QB_CONTENT_TABLE}' 已检查/创建。 (Table '{QB_CONTENT_TABLE}' checked/created.)"
                    )
                else:
                    _mysql_repo_logger.warning(
                        f"实体类型 '{entity_type}' 的表结构定义未找到。 (Table structure definition not found for entity type '{entity_type}'.)"
                    )

    def _get_table_info(self, entity_type: str) -> tuple[str, str]:
        """
        辅助方法：根据实体类型获取对应的表名和主键列名。
        (Helper method: Gets the corresponding table name and primary key column name based on entity type.)
        对于具有复合主键的表（如question_bank_contents），返回主要的ID列。
        (For tables with composite primary keys (e.g., question_bank_contents), returns the main ID column.)
        """
        if entity_type == "user":
            return USER_TABLE, "uid"
        elif entity_type == "paper":
            return PAPER_TABLE, "paper_id"
        elif entity_type == "question_bank_metadata":
            return QB_METADATA_TABLE, "id"
        elif entity_type == "question_bank_contents" or entity_type.startswith(
            QB_CONTENT_ENTITY_TYPE_PREFIX
        ):
            # 题库内容使用 difficulty_id 作为主要标识符，content_id 作为次要标识符
            # (Question bank content uses difficulty_id as the primary identifier, content_id as secondary)
            return QB_CONTENT_TABLE, "difficulty_id"
        else:
            _mysql_repo_logger.error(
                f"未知的实体类型，无法映射到表名 (Unknown entity type, cannot map to table name): {entity_type}"
            )
            raise ValueError(
                f"不支持的实体类型 (MySQL) (Unsupported entity type (MySQL)): {entity_type}"
            )

    def _deserialize_json_fields(
        self, entity_type: str, record: Dict[str, Any]
    ) -> Dict[str, Any]:
        """辅助方法：反序列化记录中可能的JSON字符串字段。(Helper: Deserialize potential JSON string fields in a record.)"""
        if not record:
            return record

        json_fields_map = {
            "user": ["tags"],
            "paper": ["paper_questions", "submitted_answers_card"],
            "question_bank_contents": ["questions"],
            # QB_CONTENT_ENTITY_TYPE_PREFIX: ["questions"], # 如果动态匹配也用这个
        }
        # Normalize entity_type for qb_content
        normalized_entity_type = (
            "question_bank_contents"
            if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX)
            else entity_type
        )

        fields_to_deserialize = json_fields_map.get(normalized_entity_type, [])

        for key in fields_to_deserialize:
            value = record.get(key)
            if isinstance(value, str):
                try:
                    record[key] = json.loads(value)
                except json.JSONDecodeError:
                    _mysql_repo_logger.warning(
                        f"反序列化字段 '{key}' 失败，值为非JSON字符串: '{value[:50]}...' (Failed to deserialize field '{key}', value is not a JSON string: '{value[:50]}...')"
                    )
                    # 保留为原始字符串或设置为None/[]取决于业务需求 (Keep as original string or set to None/[] depending on business needs)
        return record

    def _serialize_json_fields(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """辅助方法：序列化实体数据中需要存储为JSON字符串的字段。(Helper: Serialize fields in entity data that need to be stored as JSON strings.)"""
        data_copy = entity_data.copy()  # 操作副本 (Operate on a copy)
        json_fields_map = {
            "user": ["tags"],
            "paper": ["paper_questions", "submitted_answers_card"],
            "question_bank_contents": ["questions"],
            # QB_CONTENT_ENTITY_TYPE_PREFIX: ["questions"],
        }
        normalized_entity_type = (
            "question_bank_contents"
            if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX)
            else entity_type
        )
        fields_to_serialize = json_fields_map.get(normalized_entity_type, [])

        for key in fields_to_serialize:
            if key in data_copy and isinstance(data_copy[key], (dict, list)):
                data_copy[key] = json.dumps(data_copy[key])
        return data_copy

    async def get_by_id(
        self, entity_type: str, entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """通过ID从MySQL数据库中检索单个实体。(Retrieves a single entity by ID from the MySQL database.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None

        table_name, id_column = self._get_table_info(entity_type)

        # 特殊处理题库内容实体类型 (Special handling for question bank content entity type)
        # 假设 entity_id 对于 qb_content 对应 difficulty_id，并使用默认 content_id
        # (Assume entity_id for qb_content corresponds to difficulty_id, using default content_id)
        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
            actual_difficulty_id = entity_id  # 此时 entity_id 是 difficulty_id
            sql = f"SELECT * FROM {table_name} WHERE difficulty_id = %s AND content_id = %s"
            sql_params = (actual_difficulty_id, "default")
        else:
            sql = f"SELECT * FROM {table_name} WHERE {id_column} = %s"
            sql_params = (entity_id,)

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                try:
                    await cur.execute(sql, sql_params)
                    record = await cur.fetchone()
                    if record:
                        record = self._deserialize_json_fields(entity_type, record)
                        # 为题库内容适配返回结构 (Adapt return structure for qb_content)
                        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
                            return {
                                "id": record["difficulty_id"],
                                "questions": record.get("questions", []),
                            }
                    return record
                except OperationalError as e:
                    _mysql_repo_logger.error(
                        f"执行 get_by_id (实体类型 (Entity Type): {entity_type}, ID: {entity_id}) 时出错 (Error): {e}",
                        exc_info=True,
                    )
                    return None

    async def get_all(
        self, entity_type: str, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """从MySQL数据库检索指定类型的所有实体，支持分页。(Retrieves all entities of a specified type from MySQL, with pagination.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None
        table_name, id_column = self._get_table_info(entity_type)
        order_by_clause = (
            f"ORDER BY {id_column}"
            if id_column and not entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX)
            else ""
        )  # qb_content 可能没有单一主键排序

        # 题库内容通常按 difficulty_id 获取，不适合通用 get_all，除非有特定需求
        # (Question bank content usually fetched by difficulty_id, not suitable for generic get_all unless specific need)
        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
            _mysql_repo_logger.warning(
                f"get_all 不建议用于实体类型 '{entity_type}'，请使用 get_by_id (difficulty_id)。将返回空列表。 (get_all not recommended for entity type '{entity_type}', use get_by_id (difficulty_id). Returning empty list.)"
            )
            return []

        sql = f"SELECT * FROM {table_name} {order_by_clause} LIMIT %s OFFSET %s"

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                try:
                    await cur.execute(sql, (limit, skip))
                    records = await cur.fetchall()
                    return [
                        self._deserialize_json_fields(entity_type, record)
                        for record in records
                    ]
                except OperationalError as e:
                    _mysql_repo_logger.error(
                        f"执行 get_all (实体类型 (Entity Type): {entity_type}) 时出错 (Error): {e}",
                        exc_info=True,
                    )
                    return []

    async def create(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """在MySQL数据库中创建一个新实体。(Creates a new entity in the MySQL database.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None
        table_name, _ = self._get_table_info(entity_type)  # id_column 在此不直接使用

        # 序列化需要转为JSON字符串的字段
        data_to_insert = self._serialize_json_fields(entity_type, entity_data)

        # 特殊处理题库内容实体 (Special handling for qb_content)
        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
            # 确保 difficulty_id 和 content_id 存在
            # entity_data["id"] 应该映射到 difficulty_id
            data_to_insert["difficulty_id"] = entity_data.get(
                "id", data_to_insert.get("difficulty_id")
            )
            data_to_insert.pop("id", None)  # 移除原始id字段，如果存在
            data_to_insert["content_id"] = data_to_insert.get(
                "content_id", "default"
            )  # 默认 content_id

        cols = ", ".join(
            f"`{k}`" for k in data_to_insert.keys()
        )  # 列名使用反引号避免关键字冲突
        placeholders = ", ".join(["%s"] * len(data_to_insert))
        sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                try:
                    await cur.execute(sql, tuple(data_to_insert.values()))
                    if cur.rowcount == 1:  # 确保有一行被插入
                        # 对于非自增主键，MySQL的lastrowid可能不适用，返回原始数据
                        # (For non-auto-increment PKs, MySQL lastrowid may not apply, return original data)
                        # 返回原始 entity_data (未序列化JSON的) 以保持接口一致性
                        return entity_data
                    else:
                        raise OperationalError(
                            "创建操作影响了0行记录。 (Create operation affected 0 rows.)"
                        )
                except IntegrityError as e:  # 主键冲突等
                    _mysql_repo_logger.error(
                        f"创建实体 (类型 (Type): {entity_type}) 时发生完整性错误 (IntegrityError): {e}",
                        exc_info=True,
                    )
                    raise ValueError(
                        f"实体创建因完整性约束（如重复ID）失败 (Entity creation failed due to integrity constraint (e.g., duplicate ID)): {entity_type}。"
                    ) from e
                except OperationalError as e:
                    _mysql_repo_logger.error(
                        f"执行 create (实体类型 (Entity Type): {entity_type}) 时出错 (Error): {e}",
                        exc_info=True,
                    )
                    raise

    async def update(
        self, entity_type: str, entity_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """通过ID在MySQL数据库中更新现有实体。(Updates an existing entity by ID in the MySQL database.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None
        table_name, id_column = self._get_table_info(entity_type)

        if not update_data:  # 如果没有提供更新数据，则直接返回当前实体
            return await self.get_by_id(entity_type, entity_id)

        data_to_update = self._serialize_json_fields(entity_type, update_data)

        set_clause = ", ".join([f"`{col}` = %s" for col in data_to_update.keys()])
        sql_params_list: List[Any] = list(data_to_update.values())

        # 特殊处理题库内容实体 (Special handling for qb_content)
        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
            sql = f"UPDATE {table_name} SET {set_clause} WHERE difficulty_id = %s AND content_id = %s"
            sql_params_list.extend([entity_id, "default"])  # entity_id is difficulty_id
        else:
            sql = f"UPDATE {table_name} SET {set_clause} WHERE `{id_column}` = %s"
            sql_params_list.append(entity_id)

        sql_params = tuple(sql_params_list)

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                try:
                    await cur.execute(sql, sql_params)
                    if cur.rowcount > 0:  # 如果有行被更新
                        return await self.get_by_id(
                            entity_type, entity_id
                        )  # 获取并返回更新后的记录
                    _mysql_repo_logger.warning(
                        f"更新操作未影响任何行 (Update operation affected 0 rows): 类型 (Type)='{entity_type}', ID='{entity_id}'"
                    )
                    return None  # 未找到匹配记录或未更新 (No matching record found or not updated)
                except OperationalError as e:
                    _mysql_repo_logger.error(
                        f"执行 update (实体类型 (Entity Type): {entity_type}, ID: {entity_id}) 时出错 (Error): {e}",
                        exc_info=True,
                    )
                    return None

    async def delete(self, entity_type: str, entity_id: str) -> bool:
        """通过ID从MySQL数据库中删除实体。(Deletes an entity by ID from the MySQL database.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None
        table_name, id_column = self._get_table_info(entity_type)

        # 特殊处理题库内容实体 (Special handling for qb_content)
        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
            sql = (
                f"DELETE FROM {table_name} WHERE difficulty_id = %s AND content_id = %s"
            )
            sql_params = (entity_id, "default")  # entity_id is difficulty_id
        else:
            sql = f"DELETE FROM {table_name} WHERE `{id_column}` = %s"
            sql_params = (entity_id,)

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(sql, sql_params)
                    return (
                        cur.rowcount > 0
                    )  # rowcount 表示影响的行数 (rowcount indicates affected rows)
                except OperationalError as e:
                    _mysql_repo_logger.error(
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
        """根据一组条件从MySQL数据库查询实体。(Queries entities from MySQL based on a set of conditions.)"""
        if not self.pool:
            await self.connect()
        assert self.pool is not None
        table_name, id_column = self._get_table_info(entity_type)
        order_by_clause = (
            f"ORDER BY `{id_column}`"
            if id_column and not entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX)
            else ""
        )

        where_clauses = []
        sql_params_list: List[Any] = []
        for key, value in conditions.items():
            # 对于JSON字段的查询，直接比较可能不准确，取决于MySQL版本和JSON函数的使用。
            # (For JSON field queries, direct comparison might be inaccurate, depending on MySQL version and JSON function usage.)
            # 此处简单处理，高级查询可能需要json_extract等。
            # (Simple handling here; advanced queries might need json_extract, etc.)
            if isinstance(
                value, (dict, list)
            ):  # 如果查询条件的值是字典或列表，尝试序列化为JSON字符串进行比较
                where_clauses.append(f"`{key}` = %s")
                sql_params_list.append(json.dumps(value))
            else:
                where_clauses.append(f"`{key}` = %s")
                sql_params_list.append(value)

        where_sql = (
            " AND ".join(where_clauses) if where_clauses else "1=1"
        )  # 如果没有条件，则选择所有
        sql = f"SELECT * FROM {table_name} WHERE {where_sql} {order_by_clause} LIMIT %s OFFSET %s"
        sql_params_list.extend([limit, skip])
        sql_params = tuple(sql_params_list)

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                try:
                    await cur.execute(sql, sql_params)
                    records = await cur.fetchall()
                    deserialized_records = [
                        self._deserialize_json_fields(entity_type, record)
                        for record in records
                    ]

                    # 特殊处理题库内容返回结构 (Special handling for qb_content return structure)
                    if (
                        entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX)
                        and deserialized_records
                    ):
                        return [
                            {
                                "id": r["difficulty_id"],
                                "questions": r.get("questions", []),
                            }
                            for r in deserialized_records
                        ]
                    return deserialized_records
                except OperationalError as e:
                    _mysql_repo_logger.error(
                        f"执行 query (实体类型 (Entity Type): {entity_type}) 时出错 (Error): {e}",
                        exc_info=True,
                    )
                    return []

    async def get_all_entity_types(self) -> List[str]:
        """返回此存储库已知或预期管理的所有实体类型的列表 (基于定义的表常量)。
        (Returns a list of all entity types known or expected to be managed by this repository (based on defined table constants).)
        """
        return [
            USER_TABLE,
            PAPER_TABLE,
            QB_METADATA_TABLE,
            QB_CONTENT_TABLE,
            QB_CONTENT_ENTITY_TYPE_PREFIX + "*",
        ]  # 使用通配符表示动态题库内容

    async def persist_all_data(self) -> None:
        """对于MySQL，数据是实时写入的，此方法为空操作。
        (For MySQL, data is written live, so this method is a no-op.)"""
        _mysql_repo_logger.info(
            "MySQLStorageRepository: 'persist_all_data' 被调用 (空操作，数据实时持久化)。 (Called (no-op, data is persisted live).)"
        )
        pass


__all__ = [
    "MySQLStorageRepository"  # 导出MySQL存储库类 (Export MySQL repository class)
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了MySQL数据存储库的实现。
    # (This module should not be executed as the main script. It defines the MySQL data storage repository implementation.)
    _mysql_repo_logger.info(f"模块 {__name__} 定义了MySQL存储库，不应直接执行。")
    print(
        f"模块 {__name__} 定义了MySQL存储库，不应直接执行。 (This module defines the MySQL repository and should not be executed directly.)"
    )
