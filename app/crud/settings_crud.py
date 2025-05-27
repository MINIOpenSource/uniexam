# -*- coding: utf-8 -*-
# region 模块导入
import json
import asyncio # 用于异步锁
from pathlib import Path # 用于处理文件路径
from typing import Dict, Any, Optional
import logging

# 使用相对导入从同级 core 包导入配置管理功能
from .core.config import settings, update_and_persist_settings, Settings
# endregion

# region 全局变量与初始化
# 获取本模块的logger实例
_settings_crud_logger = logging.getLogger(__name__)
# endregion

# region Settings CRUD 类
class SettingsCRUD:
    """
    管理应用配置 (settings.json) 的读取和更新操作。
    此类作为通过API管理 settings.json 的接口。
    它依赖于 app.core.config 中的全局 settings 对象和相关函数来处理配置的加载、验证和持久化。
    """

    def __init__(self):
        """
        初始化 SettingsCRUD。
        配置的实际加载和管理由 app.core.config 中的全局 settings 对象处理。
        """
        # settings 对象已在 app.core.config 中全局初始化并加载
        # self.settings_file_path 指向由全局 settings 实例管理的配置文件路径
        self.settings_file_path: Path = settings.get_db_file_path("settings")

    def get_current_settings_from_file(self) -> Dict[str, Any]:
        """
        直接从 settings.json 文件读取当前的原始配置内容。
        此方法主要用于Admin界面展示用户在文件中实际保存了什么，
        因为它可能与内存中经过 .env 环境变量覆盖的全局 settings 对象有所不同。

        返回:
            从 settings.json 加载的配置字典。
            如果文件不存在或无效，则返回空字典，并记录错误。
        """
        if self.settings_file_path.exists() and self.settings_file_path.is_file():
            try:
                with open(self.settings_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                _settings_crud_logger.error(
                    f"从 '{self.settings_file_path}' 读取配置失败: {e}"
                )
                return {} # 返回空字典表示读取失败或文件无效
        _settings_crud_logger.info(f"配置文件 '{self.settings_file_path}' 未找到，返回空配置。")
        return {} # 文件不存在

    def get_active_settings(self) -> Settings:
        """
        获取当前内存中活动的、经过 .env 覆盖和Pydantic验证的全局配置对象。
        这是应用当前实际使用的配置。

        返回:
            全局 Settings Pydantic模型实例。
        """
        return settings # 直接返回已加载的全局 settings 对象

    async def update_settings_file_and_reload(
        self,
        new_settings_data: Dict[str, Any]
    ) -> Settings:
        """
        异步更新 settings.json 文件中的配置项，并触发全局配置的重新加载。
        此方法会调用 app.core.config 中的 update_and_persist_settings 函数，
        该函数负责验证、合并.env、写入文件和更新全局配置实例。

        参数:
            new_settings_data: 一个包含要更新的配置项的字典。
                               例如: {"token_expiry_hours": 48, "app_name": "新考试系统"}
                               注意：此字典中的键应与 Settings Pydantic模型中的字段名匹配。

        返回:
            更新并重新加载后的全局 Settings Pydantic模型实例。

        异常:
            ValueError: 如果提供的配置数据无效（例如，不符合Pydantic模型约束）。
            IOError: 如果写入 settings.json 文件失败。
            RuntimeError: 如果在更新过程中发生其他未知错误。
        """
        _settings_crud_logger.info(f"尝试通过CRUD更新应用配置: {new_settings_data}")
        try:
            # update_and_persist_settings 会处理验证、合并.env、写入文件和更新全局实例
            updated_settings_instance = await update_and_persist_settings(new_settings_data)
            _settings_crud_logger.info("应用配置已成功通过CRUD更新并重新加载。")
            return updated_settings_instance
        except ValueError as e_val: # 通常是 Pydantic ValidationError
            _settings_crud_logger.error(f"通过CRUD更新配置时数据验证失败: {e_val}")
            raise  # 重新抛出验证错误，让API层处理并返回给客户端
        except IOError as e_io:
            _settings_crud_logger.error(f"通过CRUD更新配置文件时发生IO错误: {e_io}")
            raise  # 重新抛出IO错误
        except Exception as e: # 捕获其他可能的意外错误
            _settings_crud_logger.error(f"通过CRUD更新配置时发生未知错误: {e}", exc_info=True)
            raise RuntimeError(f"通过CRUD更新配置时发生未知错误: {str(e)}")

# endregion

# region CRUD实例 (可选的单例模式或在需要时直接实例化)
# settings_crud = SettingsCRUD() # 如果希望在其他地方直接导入此实例
# 通常，CRUD实例会在路由层或服务层被创建和使用。
# endregion
