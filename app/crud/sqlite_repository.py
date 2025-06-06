# -*- coding: utf-8 -*-
"""
SQLite 数据存储库实现模块。
(SQLite Data Storage Repository Implementation Module.)

该模块提供了 `IDataStorageRepository` 接口的一个具体实现，
使用 SQLite 作为后端数据库。它利用 `aiosqlite` 库进行异步数据库操作。
JSON 字段在此适配器中将作为 TEXT 类型存储，并在读写时进行序列化/反序列化。
(This module provides a concrete implementation of the `IDataStorageRepository` interface,
using SQLite as the backend database. It utilizes the `aiosqlite` library for
asynchronous database operations. JSON fields are stored as TEXT type in this adapter
and are serialized/deserialized during read/write operations.)
"""

import json  # 用于JSON序列化和反序列化 (For JSON serialization and deserialization)
import logging
import sqlite3  # 用于特定的SQLite错误类型 (For specific SQLite error types)
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiosqlite  # type: ignore # aiosqlite 可能没有完整的类型存根 (aiosqlite might not have complete type stubs)

from app.core.interfaces import (
    IDataStorageRepository,
)  # 导入抽象基类 (Import abstract base class)

# QB_CONTENT_ENTITY_TYPE_PREFIX 用于动态识别题库内容实体类型
# (QB_CONTENT_ENTITY_TYPE_PREFIX for dynamically identifying QB content entity types)
from .qb_crud import QB_CONTENT_ENTITY_TYPE_PREFIX

_sqlite_repo_logger = logging.getLogger(__name__)  # 获取本模块的日志记录器实例

# 表名常量 (Table name constants)
USER_TABLE = "users"  # 用户表 (Users table)
PAPER_TABLE = "papers"  # 试卷表 (Papers table)
QB_METADATA_TABLE = (
    "question_bank_metadata"  # 题库元数据表 (Question bank metadata table)
)
QB_CONTENT_TABLE = "question_bank_contents"  # 题库内容表 (Question bank contents table)


class SQLiteStorageRepository(IDataStorageRepository):
    """
    一个使用 SQLite 进行持久化的数据存储库实现。
    此类实现了 IDataStorageRepository 接口中定义的所有异步方法。
    (A data storage repository implementation using SQLite for persistence.
    This class implements all asynchronous methods defined in the IDataStorageRepository interface.)
    """

    def __init__(self, db_file_path: Union[str, Path]):
        """
        初始化 SQLiteStorageRepository。
        (Initializes the SQLiteStorageRepository.)

        参数 (Args):
            db_file_path (Union[str, Path]): SQLite 数据库文件的路径。
                                             (Path to the SQLite database file.)
        """
        self.db_file_path = Path(db_file_path)
        _sqlite_repo_logger.info(
            f"SQLiteStorageRepository 已使用数据库路径初始化 (SQLiteStorageRepository initialized with DB path): {self.db_file_path}"
        )

    async def connect(self) -> None:
        """
        确保数据库文件所在的目录存在。对于 `aiosqlite`，连接通常按需建立。
        (Ensures the directory for the database file exists. For `aiosqlite`, connections are typically on-demand.)
        """
        try:
            self.db_file_path.parent.mkdir(
                parents=True, exist_ok=True
            )  # 确保目录存在 (Ensure directory exists)
            _sqlite_repo_logger.info(
                f"SQLiteStorageRepository: 'connect' 被调用。数据库目录已确保 (DB directory ensured): {self.db_file_path.parent}"
            )
        except Exception as e:
            _sqlite_repo_logger.error(
                f"为SQLite确保数据库目录时出错 (Error ensuring DB directory for SQLite): {e}",
                exc_info=True,
            )
            raise

    async def disconnect(self) -> None:
        """
        关闭与数据存储的连接。对于 `aiosqlite`，通常为空操作。
        (Closes the connection. For `aiosqlite`, this is typically a no-op.)
        """
        _sqlite_repo_logger.info(
            "SQLiteStorageRepository: 'disconnect' 被调用 (空操作) (Called (no-op))."
        )
        pass

    async def init_storage_if_needed(
        self, entity_type: str, default_data: Optional[Any] = None
    ) -> None:
        """
        确保指定实体类型的数据库表存在。如果不存在，则创建它。
        (Ensures the table for the specified entity type exists. Creates it if not.)
        `default_data` 参数在此实现中未使用。(The `default_data` parameter is not used in this implementation.)
        """
        async with aiosqlite.connect(self.db_file_path) as db:
            if entity_type == "user":
                await db.execute(
                    f"""CREATE TABLE IF NOT EXISTS {USER_TABLE} (
                        uid TEXT PRIMARY KEY, nickname TEXT, email TEXT, qq TEXT,
                        tags TEXT, hashed_password TEXT )"""
                )
                _sqlite_repo_logger.info(
                    f"表 '{USER_TABLE}' 已检查/创建。(Table '{USER_TABLE}' checked/created.)"
                )
            elif entity_type == "paper":
                await db.execute(
                    f"""CREATE TABLE IF NOT EXISTS {PAPER_TABLE} (
                        paper_id TEXT PRIMARY KEY,
                        user_uid TEXT,
                        creation_time_utc TEXT,
                        creation_ip TEXT,
                        difficulty TEXT,
                        paper_questions TEXT,
                        score INTEGER,
                        submitted_answers_card TEXT,
                        submission_time_utc TEXT,
                        submission_ip TEXT,
                        pass_status TEXT,
                        passcode TEXT,
                        last_update_time_utc TEXT,
                        last_update_ip TEXT,
                        subjective_questions_count INTEGER DEFAULT 0,
                        graded_subjective_questions_count INTEGER DEFAULT 0,
                        pending_manual_grading_count INTEGER DEFAULT 0,
                        total_score REAL DEFAULT 0.0
                        )"""
                )
                _sqlite_repo_logger.info(
                    f"表 '{PAPER_TABLE}' 已检查/创建。(Table '{PAPER_TABLE}' checked/created.)"
                )
            elif entity_type == "question_bank_metadata":
                await db.execute(
                    f"""CREATE TABLE IF NOT EXISTS {QB_METADATA_TABLE} (
                        id TEXT PRIMARY KEY, name TEXT, description TEXT,
                        default_questions INTEGER, total_questions INTEGER )"""
                )
                _sqlite_repo_logger.info(
                    f"表 '{QB_METADATA_TABLE}' 已检查/创建。(Table '{QB_METADATA_TABLE}' checked/created.)"
                )
            elif entity_type == "question_bank_contents" or entity_type.startswith(
                QB_CONTENT_ENTITY_TYPE_PREFIX
            ):
                await db.execute(
                    f"""CREATE TABLE IF NOT EXISTS {QB_CONTENT_TABLE} (
                        difficulty_id TEXT, content_id TEXT, questions TEXT,
                        PRIMARY KEY (difficulty_id, content_id) )"""
                )
                _sqlite_repo_logger.info(
                    f"表 '{QB_CONTENT_TABLE}' 已检查/创建。(Table '{QB_CONTENT_TABLE}' checked/created.)"
                )
            else:
                _sqlite_repo_logger.warning(
                    f"实体类型 '{entity_type}' 的表结构定义未找到。(Table definition for entity type '{entity_type}' not found.)"
                )
            await db.commit()

    def _get_table_info(self, entity_type: str) -> tuple[str, str]:
        """
        辅助方法：根据实体类型获取对应的表名和主键列名。
        (Helper method: Gets table name and primary key column based on entity type.)
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
            return QB_CONTENT_TABLE, "difficulty_id"  # 主键是复合的 (PK is composite)
        else:
            _sqlite_repo_logger.error(
                f"未知的实体类型，无法映射到表名 (Unknown entity type, cannot map to table name): {entity_type}"
            )
            raise ValueError(
                f"不支持的实体类型 (SQLite) (Unsupported entity type (SQLite)): {entity_type}"
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
        }
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
                    _sqlite_repo_logger.warning(
                        f"反序列化字段 '{key}' 失败，非JSON字符串: '{value[:50]}...' (Failed to deserialize field '{key}', not JSON string: '{value[:50]}...')"
                    )
        return record

    def _serialize_json_fields(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """辅助方法：序列化实体数据中需存为JSON字符串的字段。(Helper: Serialize fields in entity data to be stored as JSON strings.)"""
        data_copy = entity_data.copy()
        json_fields_map = {
            "user": ["tags"],
            "paper": ["paper_questions", "submitted_answers_card"],
            "question_bank_contents": ["questions"],
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
        """通过ID从SQLite数据库中检索单个实体。(Retrieves a single entity by ID from SQLite.)"""
        if not self.db_file_path:
            raise ValueError("数据库文件路径未设置。(DB file path not set.)")
        table_name, id_column = self._get_table_info(entity_type)
        sql_params: List[Any] = []

        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):  # 题库内容特殊处理
            sql = (
                f"SELECT * FROM {table_name} WHERE difficulty_id = ? AND content_id = ?"
            )
            sql_params = [entity_id, "default"]  # 假设 content_id 为 'default'
        else:
            sql = f"SELECT * FROM {table_name} WHERE {id_column} = ?"
            sql_params = [entity_id]

        async with aiosqlite.connect(self.db_file_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.cursor() as cur:
                try:
                    await cur.execute(sql, tuple(sql_params))
                    row = await cur.fetchone()
                    if row:
                        data = self._deserialize_json_fields(entity_type, dict(row))
                        if entity_type.startswith(
                            QB_CONTENT_ENTITY_TYPE_PREFIX
                        ):  # 返回题库内容特定结构
                            return {
                                "id": data["difficulty_id"],
                                "questions": data.get("questions", []),
                            }
                        return data
                    return None
                except sqlite3.OperationalError as e:
                    _sqlite_repo_logger.error(
                        f"执行 get_by_id (实体类型 (Entity Type): {entity_type}, ID: {entity_id}) 时出错 (Error): {e}",
                        exc_info=True,
                    )
                    if "no such table" in str(e).lower():
                        await self.init_storage_if_needed(entity_type)
                    return None

    async def get_all(
        self, entity_type: str, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """从SQLite数据库检索指定类型的所有实体，支持分页。(Retrieves all entities of a type from SQLite, with pagination.)"""
        if not self.db_file_path:
            raise ValueError("数据库文件路径未设置。(DB file path not set.)")
        table_name, id_column = self._get_table_info(entity_type)
        order_by_clause = (
            f"ORDER BY {id_column}"
            if id_column and not entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX)
            else ""
        )

        if entity_type.startswith(
            QB_CONTENT_ENTITY_TYPE_PREFIX
        ):  # 题库内容不适合通用 get_all
            _sqlite_repo_logger.warning(
                f"get_all 不建议用于实体类型 '{entity_type}'。将返回空列表。(get_all not recommended for entity type '{entity_type}'. Returning empty list.)"
            )
            return []

        sql = f"SELECT * FROM {table_name} {order_by_clause} LIMIT ? OFFSET ?"

        async with aiosqlite.connect(self.db_file_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.cursor() as cur:
                try:
                    await cur.execute(sql, (limit, skip))
                    rows = await cur.fetchall()
                    return [
                        self._deserialize_json_fields(entity_type, dict(row))
                        for row in rows
                    ]
                except sqlite3.OperationalError as e:
                    _sqlite_repo_logger.error(
                        f"执行 get_all (实体类型 (Entity Type): {entity_type}) 时出错 (Error): {e}",
                        exc_info=True,
                    )
                    if "no such table" in str(e).lower():
                        await self.init_storage_if_needed(entity_type)
                    return []

    async def create(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """在SQLite数据库中创建一个新实体。(Creates a new entity in SQLite.)"""
        if not self.db_file_path:
            raise ValueError("数据库文件路径未设置。(DB file path not set.)")
        table_name, _ = self._get_table_info(entity_type)
        data_to_insert = self._serialize_json_fields(entity_type, entity_data)

        if entity_type.startswith(
            QB_CONTENT_ENTITY_TYPE_PREFIX
        ):  # 处理题库内容的复合键和数据结构
            data_to_insert["difficulty_id"] = entity_data.get(
                "id", data_to_insert.get("difficulty_id")
            )
            data_to_insert.pop("id", None)  # 移除原 'id'
            data_to_insert["content_id"] = data_to_insert.get("content_id", "default")

        cols = ", ".join(
            f"`{k}`" for k in data_to_insert.keys()
        )  # SQLite中反引号可选，但为一致性可保留
        placeholders = ", ".join(["?"] * len(data_to_insert))
        sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"

        async with aiosqlite.connect(self.db_file_path) as db:
            try:
                await db.execute(sql, tuple(data_to_insert.values()))
                await db.commit()
                return entity_data  # 返回原始数据作为确认 (Return original data as confirmation)
            except sqlite3.IntegrityError as e:
                _sqlite_repo_logger.error(
                    f"创建实体 (类型 (Type): {entity_type}) 时发生完整性错误 (IntegrityError): {e}",
                    exc_info=True,
                )
                raise ValueError(
                    f"实体创建因完整性约束（如重复ID）失败 (Entity creation failed due to integrity constraint (e.g., duplicate ID)): {entity_type}。"
                ) from e
            except sqlite3.OperationalError as e:
                _sqlite_repo_logger.error(
                    f"执行 create (实体类型 (Entity Type): {entity_type}) 时出错 (Error): {e}",
                    exc_info=True,
                )
                if "no such table" in str(e).lower():
                    await self.init_storage_if_needed(entity_type)
                    await db.execute(sql, tuple(data_to_insert.values()))
                    await db.commit()
                    return entity_data
                raise

    async def update(
        self, entity_type: str, entity_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """通过ID在SQLite数据库中更新现有实体。(Updates an existing entity by ID in SQLite.)"""
        if not self.db_file_path:
            raise ValueError("数据库文件路径未设置。(DB file path not set.)")
        table_name, id_column = self._get_table_info(entity_type)
        if not update_data:
            return await self.get_by_id(entity_type, entity_id)

        data_to_update = self._serialize_json_fields(entity_type, update_data)
        set_clause = ", ".join([f"`{col}` = ?" for col in data_to_update.keys()])
        sql_params_list: List[Any] = list(data_to_update.values())

        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
            sql = f"UPDATE {table_name} SET {set_clause} WHERE difficulty_id = ? AND content_id = ?"
            sql_params_list.extend([entity_id, "default"])
        else:
            sql = f"UPDATE {table_name} SET {set_clause} WHERE `{id_column}` = ?"
            sql_params_list.append(entity_id)
        sql_params = tuple(sql_params_list)

        async with aiosqlite.connect(self.db_file_path) as db:
            try:
                cursor = await db.execute(sql, sql_params)
                await db.commit()
                if cursor.rowcount > 0:
                    return await self.get_by_id(entity_type, entity_id)
                return None
            except sqlite3.OperationalError as e:
                _sqlite_repo_logger.error(
                    f"执行 update (实体类型 (Entity Type): {entity_type}, ID: {entity_id}) 时出错 (Error): {e}",
                    exc_info=True,
                )
                if "no such table" in str(e).lower():
                    await self.init_storage_if_needed(entity_type)
                return None

    async def delete(self, entity_type: str, entity_id: str) -> bool:
        """通过ID从SQLite数据库中删除实体。(Deletes an entity by ID from SQLite.)"""
        if not self.db_file_path:
            raise ValueError("数据库文件路径未设置。(DB file path not set.)")
        table_name, id_column = self._get_table_info(entity_type)
        sql_params_list: List[Any] = []

        if entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX):
            sql = f"DELETE FROM {table_name} WHERE difficulty_id = ? AND content_id = ?"
            sql_params_list = [entity_id, "default"]
        else:
            sql = f"DELETE FROM {table_name} WHERE `{id_column}` = ?"
            sql_params_list = [entity_id]
        sql_params = tuple(sql_params_list)

        async with aiosqlite.connect(self.db_file_path) as db:
            try:
                cursor = await db.execute(sql, sql_params)
                await db.commit()
                return cursor.rowcount > 0
            except sqlite3.OperationalError as e:
                _sqlite_repo_logger.error(
                    f"执行 delete (实体类型 (Entity Type): {entity_type}, ID: {entity_id}) 时出错 (Error): {e}",
                    exc_info=True,
                )
                if "no such table" in str(e).lower():
                    await self.init_storage_if_needed(entity_type)
                return False

    async def query(
        self,
        entity_type: str,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """根据一组条件从SQLite数据库查询实体。(Queries entities from SQLite based on a set of conditions.)"""
        if not self.db_file_path:
            raise ValueError("数据库文件路径未设置。(DB file path not set.)")
        table_name, id_column = self._get_table_info(entity_type)
        order_by_clause = (
            f"ORDER BY `{id_column}`"
            if id_column and not entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX)
            else ""
        )

        where_clauses: List[str] = []
        sql_params_list: List[Any] = []
        for key, value in conditions.items():
            where_clauses.append(f"`{key}` = ?")
            sql_params_list.append(
                json.dumps(value) if isinstance(value, (dict, list)) else value
            )

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        sql = f"SELECT * FROM {table_name} WHERE {where_sql} {order_by_clause} LIMIT ? OFFSET ?"
        sql_params_list.extend([limit, skip])
        sql_params = tuple(sql_params_list)

        async with aiosqlite.connect(self.db_file_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.cursor() as cur:
                try:
                    await cur.execute(sql, sql_params)
                    rows = await cur.fetchall()
                    results = [
                        self._deserialize_json_fields(entity_type, dict(row))
                        for row in rows
                    ]
                    if (
                        entity_type.startswith(QB_CONTENT_ENTITY_TYPE_PREFIX)
                        and results
                    ):  # 返回题库内容特定结构
                        return [
                            {
                                "id": r["difficulty_id"],
                                "questions": r.get("questions", []),
                            }
                            for r in results
                        ]
                    return results
                except sqlite3.OperationalError as e:
                    _sqlite_repo_logger.error(
                        f"执行 query (实体类型 (Entity Type): {entity_type}) 时出错 (Error): {e}",
                        exc_info=True,
                    )
                    if "no such table" in str(e).lower():
                        await self.init_storage_if_needed(entity_type)
                    return []

    async def get_all_entity_types(self) -> List[str]:
        """返回此存储库已知或预期管理的所有实体类型的列表 (基于定义的表常量)。
        (Returns a list of all entity types known/expected to be managed (based on defined table constants).)
        """
        return [
            USER_TABLE,
            PAPER_TABLE,
            QB_METADATA_TABLE,
            QB_CONTENT_TABLE,
            QB_CONTENT_ENTITY_TYPE_PREFIX + "*",
        ]  # 使用通配符表示动态题库内容

    async def persist_all_data(self) -> None:
        """对于SQLite，数据实时持久化（通过commit），此方法为空操作。(For SQLite, data is persisted live (via commit); this is a no-op.)"""
        _sqlite_repo_logger.info(
            "SQLiteStorageRepository: 'persist_all_data' 被调用 (空操作，数据实时持久化)。 (Called (no-op, data is persisted live).)"
        )
        pass


__all__ = [
    "SQLiteStorageRepository"  # 导出SQLite存储库类 (Export SQLite repository class)
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了SQLite数据存储库的实现。
    # (This module should not be executed as the main script. It defines the SQLite data storage repository implementation.)
    _sqlite_repo_logger.info(f"模块 {__name__} 定义了SQLite存储库，不应直接执行。")
    print(
        f"模块 {__name__} 定义了SQLite存储库，不应直接执行。 (This module defines the SQLite repository and should not be executed directly.)"
    )
