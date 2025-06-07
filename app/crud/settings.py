# -*- coding: utf-8 -*-
"""
应用配置管理模块 (Application Configuration Management Module)。

此模块定义了 `SettingsCRUD` 类，用于管理应用配置（通常是 `settings.json` 文件）
的读取和更新操作。它作为通过API或其他管理界面修改应用配置的接口。
此类依赖于 `app.core.config` 中定义的全局 `settings` 对象及其相关的配置处理函数，
如加载、验证和持久化配置。

(This module defines the `SettingsCRUD` class, which is used to manage the reading
and updating operations for the application's configuration (typically `settings.json`).
It serves as an interface for modifying application settings via an API or other
management interfaces. This class relies on the global `settings` object defined in
`app.core.config` and its associated configuration handling functions, such as
loading, validation, and persistence of configurations.)
"""

# region 模块导入 (Module Imports)
import json
import logging
from pathlib import Path  # 用于处理文件路径 (For handling file paths)
from typing import Any, Dict

# 使用相对导入从同级 core 包导入配置管理功能
# (Using relative import to import configuration management functions from the sibling core package)
from ..core.config import Settings, settings, update_and_persist_settings

# `Settings` Pydantic模型 (Settings Pydantic model)
# `settings` 全局配置实例 (Global settings instance)
# `update_and_persist_settings` 更新并保存配置的函数 (Function to update and persist settings)
# endregion

# region 全局变量与初始化 (Global Variables & Initialization)
_settings_crud_logger = logging.getLogger(
    __name__
)  # 获取本模块的日志记录器实例 (Logger instance for this module)
# endregion


# region Settings CRUD 类 (Settings CRUD Class)
class SettingsCRUD:
    """
    管理应用配置 (`settings.json`) 的读取和更新操作。
    此类作为通过API管理 `settings.json` 的接口。
    它依赖于 `app.core.config` 中的全局 `settings` 对象和相关函数来处理配置的加载、验证和持久化。

    (Manages read and update operations for the application configuration (`settings.json`).
    This class serves as an interface for managing `settings.json` via an API.
    It relies on the global `settings` object in `app.core.config` and related functions
    for loading, validating, and persisting configurations.)
    """

    def __init__(self):
        """
        初始化 SettingsCRUD。
        配置的实际加载和管理由 `app.core.config` 中的全局 `settings` 对象处理。
        `settings_file_path` 指向由全局 `settings` 实例管理的配置文件路径。

        (Initializes SettingsCRUD.
        The actual loading and management of configurations are handled by the global `settings`
        object in `app.core.config`. `settings_file_path` points to the configuration file
        path managed by the global `settings` instance.)
        """
        self.settings_file_path: Path = settings.get_db_file_path(
            "settings"
        )  # settings.json 的路径
        _settings_crud_logger.info(
            f"SettingsCRUD 初始化完成，配置文件路径 (SettingsCRUD initialized, config file path): '{self.settings_file_path}'"
        )

    def get_current_settings_from_file(self) -> Dict[str, Any]:
        """
        直接从 `settings.json` 文件读取当前的原始配置内容。
        此方法主要用于Admin界面展示用户在文件中实际保存了什么，
        因为它可能与内存中经过 `.env` 环境变量覆盖的全局 `settings` 对象有所不同。

        (Directly reads the current raw configuration content from the `settings.json` file.
        This method is primarily used for the Admin interface to display what the user has
        actually saved in the file, as it may differ from the global `settings` object
        in memory, which is overridden by `.env` environment variables.)

        返回 (Returns):
            Dict[str, Any]: 从 `settings.json` 加载的配置字典。
                            如果文件不存在或无效，则返回空字典，并记录错误。
                            (A dictionary loaded from `settings.json`.
                             Returns an empty dictionary if the file does not exist or is invalid,
                             and logs an error.)
        """
        _settings_crud_logger.debug(
            f"尝试从 '{self.settings_file_path}' 读取原始配置。 (Attempting to read raw config from '{self.settings_file_path}'.)"
        )
        if self.settings_file_path.exists() and self.settings_file_path.is_file():
            try:
                with open(self.settings_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                _settings_crud_logger.error(
                    f"从 '{self.settings_file_path}' 读取配置失败 (Failed to read config from '{self.settings_file_path}'): {e}"
                )
                return {}
        _settings_crud_logger.info(
            f"配置文件 '{self.settings_file_path}' 未找到，返回空配置。 (Config file '{self.settings_file_path}' not found, returning empty config.)"
        )
        return {}

    def get_active_settings(self) -> Settings:
        """
        获取当前内存中活动的、经过 `.env` 覆盖和Pydantic验证的全局配置对象。
        这是应用当前实际使用的配置。

        (Gets the currently active global configuration object in memory, which has been
        overridden by `.env` and validated by Pydantic. This is the configuration
        currently in use by the application.)

        返回 (Returns):
            Settings: 全局 `Settings` Pydantic模型实例。(The global `Settings` Pydantic model instance.)
        """
        _settings_crud_logger.debug(
            "获取活动的全局配置实例。 (Fetching active global settings instance.)"
        )
        return settings  # 直接返回已加载的全局 settings 对象 (Directly return the loaded global settings object)

    async def update_settings_file_and_reload(
        self, new_settings_data: Dict[str, Any]
    ) -> Settings:
        """
        异步更新 `settings.json` 文件中的配置项，并触发全局配置的重新加载。
        此方法会调用 `app.core.config` 中的 `update_and_persist_settings` 函数，
        该函数负责验证、合并环境变量、写入文件和更新全局配置实例。

        (Asynchronously updates configuration items in the `settings.json` file and triggers
        a reload of the global configuration. This method calls the `update_and_persist_settings`
        function from `app.core.config`, which is responsible for validation, merging
        environment variables, writing to the file, and updating the global configuration instance.)

        参数 (Args):
            new_settings_data (Dict[str, Any]): 一个包含要更新的配置项的字典。
                                               例如 (e.g.): `{"token_expiry_hours": 48, "app_name": "新考试系统"}`
                                               注意：此字典中的键应与 `Settings` Pydantic模型中的字段名匹配。
                                               (Note: Keys in this dictionary should match field names in the `Settings` Pydantic model.)
        返回 (Returns):
            Settings: 更新并重新加载后的全局 `Settings` Pydantic模型实例。
                      (The updated and reloaded global `Settings` Pydantic model instance.)
        异常 (Raises):
            ValueError: 如果提供的配置数据无效（例如，不符合Pydantic模型约束）。
                        (If the provided configuration data is invalid (e.g., does not meet Pydantic model constraints).)
            IOError: 如果写入 `settings.json` 文件失败。(If writing to the `settings.json` file fails.)
            RuntimeError: 如果在更新过程中发生其他未知错误。(If other unknown errors occur during the update process.)
        """
        _settings_crud_logger.info(
            f"尝试通过CRUD更新应用配置 (Attempting to update app config via CRUD): {new_settings_data}"
        )
        try:
            updated_settings_instance = await update_and_persist_settings(
                new_settings_data
            )
            _settings_crud_logger.info(
                "应用配置已成功通过CRUD更新并重新加载。 (App config successfully updated and reloaded via CRUD.)"
            )
            return updated_settings_instance
        except ValueError as e_val:
            _settings_crud_logger.error(
                f"通过CRUD更新配置时数据验证失败 (Data validation failed during CRUD update): {e_val}"
            )
            raise
        except IOError as e_io:
            _settings_crud_logger.error(
                f"通过CRUD更新配置文件时发生IO错误 (IOError during CRUD update of config file): {e_io}"
            )
            raise
        except Exception as e:
            _settings_crud_logger.error(
                f"通过CRUD更新配置时发生未知错误 (Unknown error during CRUD update of config): {e}",
                exc_info=True,
            )
            raise RuntimeError(
                f"通过CRUD更新配置时发生未知错误 (Unknown error during CRUD update of config): {str(e)}"
            ) from e


# endregion

__all__ = ["SettingsCRUD"]  # 导出SettingsCRUD类 (Export SettingsCRUD class)

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了应用设置的CRUD操作类。
    # (This module should not be executed as the main script. It defines the CRUD operations class for application settings.)
    _settings_crud_logger.info(
        f"模块 {__name__} 提供了应用设置的CRUD操作类，不应直接执行。"
    )
    print(
        f"模块 {__name__} 提供了应用设置的CRUD操作类，不应直接执行。 (This module provides CRUD operations class for application settings and should not be executed directly.)"
    )
