# -*- coding: utf-8 -*-
"""
app.crud 包初始化文件。

此包包含所有与数据持久化层交互的 "Create, Read, Update, Delete" (CRUD) 操作逻辑。
每个模块通常对应应用中的一个核心数据实体或配置。

主要导出的内容包括：
- 初始化的 CRUD 操作实例 (如 `user_crud_instance`)。
- CRUD 操作类的定义 (如 `UserCRUD`)，主要用于类型提示和内部逻辑。
- 数据存储库的实现类 (如 `JsonStorageRepository`)，主要用于类型提示和可能的直接使用场景。
- `initialize_crud_instances` 函数，用于在应用启动时初始化所有 CRUD 实例和数据存储库。
"""

from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.interfaces import IDataStorageRepository

from .json_repository import JsonStorageRepository
from .mysql_repository import MySQLStorageRepository
from .paper import PaperCRUD
from .postgres_repository import PostgresStorageRepository
from .qb import QuestionBankCRUD
from .redis_repository import RedisStorageRepository
from .settings import SettingsCRUD
from .sqlite_repository import SQLiteStorageRepository
from .user import UserCRUD

# 全局实例将由 initialize_crud_instances 函数设置
# (Global instances will be set by the initialize_crud_instances function)
user_crud_instance: Optional[UserCRUD] = None
paper_crud_instance: Optional[PaperCRUD] = None
qb_crud_instance: Optional[QuestionBankCRUD] = None
settings_crud_instance: Optional[SettingsCRUD] = None
repository_instance: Optional[IDataStorageRepository] = None


async def initialize_crud_instances():
    """
    异步初始化所有 CRUD 实例和底层数据存储库。

    根据 `settings.data_storage_type` 配置选择并实例化相应的数据存储库，
    然后使用该存储库实例化各个 CRUD 操作类。
    此函数应在应用启动时调用。
    """
    global \
        user_crud_instance, \
        paper_crud_instance, \
        qb_crud_instance, \
        settings_crud_instance, \
        repository_instance

    if settings.data_storage_type == "json":
        file_paths_config = {
            "user": Path(settings.database_files.users),
            "paper": Path(settings.database_files.papers),
            # TODO: 未来根据需要添加其他实体类型及其文件路径配置
            # (TODO: Add other entity types and their file paths as needed in the future)
            # "settings_app": Path("app_settings.json"), # 应用设置的JSON文件名示例
            # "question_bank_meta": Path(settings.question_library_index_file), # 题库元数据文件名示例
        }
        current_repository = JsonStorageRepository(
            file_paths_config=file_paths_config, base_data_dir=settings.data_dir
        )
    elif settings.data_storage_type == "postgres":
        current_repository = PostgresStorageRepository(
            dsn=settings.POSTGRES_DSN,
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
        )
    elif settings.data_storage_type == "mysql":
        if not all(
            [
                settings.MYSQL_HOST,
                settings.MYSQL_USER,
                settings.MYSQL_PASSWORD,
                settings.MYSQL_DB,
            ]
        ):
            raise ValueError("配置中缺少必要的MySQL连接参数。")
        current_repository = MySQLStorageRepository(
            host=settings.MYSQL_HOST,
            port=(settings.MYSQL_PORT if settings.MYSQL_PORT is not None else 3306),
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            db=settings.MYSQL_DB,
        )
    elif settings.data_storage_type == "redis":
        current_repository = RedisStorageRepository(
            redis_url=settings.REDIS_URL,
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
        )
    elif settings.data_storage_type == "sqlite":
        db_path = Path(settings.SQLITE_DB_PATH)
        current_repository = SQLiteStorageRepository(db_file_path=db_path)
    else:
        raise ValueError(f"不支持的数据存储类型: {settings.data_storage_type}")

    await current_repository.connect()
    repository_instance = current_repository

    if repository_instance is None:
        raise RuntimeError("存储库实例未能成功创建。")

    user_crud_instance = UserCRUD(repository=repository_instance)
    await user_crud_instance.initialize_storage()

    qb_crud_instance = QuestionBankCRUD(repository=repository_instance)
    await qb_crud_instance.initialize_storage()

    paper_crud_instance = PaperCRUD(
        repository=repository_instance, qb_crud_instance=qb_crud_instance
    )
    await paper_crud_instance.initialize_storage()

    settings_crud_instance = (
        SettingsCRUD()
    )  # SettingsCRUD 可能不直接使用通用的 repository 实例，它有自己的配置文件处理逻辑
    # (SettingsCRUD might not use the generic repository instance directly; it has its own config file handling logic)

    assert user_crud_instance is not None, "UserCRUD 未初始化成功"
    assert paper_crud_instance is not None, "PaperCRUD 未初始化成功"
    assert qb_crud_instance is not None, "QuestionBankCRUD 未初始化成功"
    assert settings_crud_instance is not None, "SettingsCRUD 未初始化成功"
    assert repository_instance is not None, "存储库实例在初始化后仍为None"


__all__ = [
    # 已初始化的实例 (推荐在大部分应用逻辑中使用)
    # (Initialized instances (preferred for use in most app logic))
    "user_crud_instance",
    "paper_crud_instance",
    "qb_crud_instance",
    "settings_crud_instance",
    "repository_instance",
    # 初始化函数
    # (Initialization function)
    "initialize_crud_instances",
    # CRUD 类定义 (主要用于类型提示和内部逻辑)
    # (CRUD Class definitions (for type hinting, internal use))
    "UserCRUD",
    "PaperCRUD",
    "QuestionBankCRUD",  # 注意: 这是实际的类名 (Note: This is the actual class name)
    "SettingsCRUD",
    # 存储库类定义 (主要用于类型提示和特定场景)
    # (Repository Class definitions (for type hinting, specific scenarios))
    "JsonStorageRepository",
    "PostgresStorageRepository",
    "MySQLStorageRepository",
    "RedisStorageRepository",
    "SQLiteStorageRepository",
]
