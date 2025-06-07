# -*- coding: utf-8 -*-
"""
app.crud.settings.SettingsCRUD 类的单元测试。
(Unit tests for the app.crud.settings.SettingsCRUD class.)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from app.core.config import Settings as ActualSettings  # 用于类型提示和创建模拟对象
from app.crud.settings import SettingsCRUD

# (For type hinting and creating mock objects)

# (Although CRUD doesn't use it directly, tests might involve it for updates)

# region Fixtures (测试固件)


@pytest.fixture
def mock_tmp_settings_file(tmp_path: Path) -> Path:
    """创建一个临时的 settings.json 文件路径供测试使用。"""
    # (Creates a temporary settings.json file path for testing.)
    return tmp_path / "test_app_settings.json"


@pytest.fixture
def settings_crud_instance(mocker, mock_tmp_settings_file: Path) -> SettingsCRUD:
    """
    提供一个 SettingsCRUD 实例。
    它会模拟全局的 `app.core.config.settings` 对象的 `get_db_file_path` 方法
    以指向一个临时文件。
    (Provides a SettingsCRUD instance.
     It mocks the `get_db_file_path` method of the global `app.core.config.settings` object
     to point to a temporary file.)
    """
    # 模拟全局 settings 对象，特别是其获取设置文件路径的方法
    # (Mock the global settings object, especially its method for getting settings file path)
    mock_global_app_settings = MagicMock(spec=ActualSettings)
    mock_global_app_settings.get_db_file_path = MagicMock(
        return_value=mock_tmp_settings_file
    )

    # SettingsCRUD 在其模块顶层导入了 settings: from app.core.config import settings
    # (SettingsCRUD imports settings at its module top: from app.core.config import settings)
    # 所以我们需要 patch 'app.crud.settings.settings'
    # (So we need to patch 'app.crud.settings.settings')
    mocker.patch("app.crud.settings.settings", mock_global_app_settings)

    return SettingsCRUD()


# endregion

# region get_current_settings_from_file 测试 (get_current_settings_from_file Tests)


@pytest.mark.asyncio  # 虽然get_current_settings_from_file本身不是async，但测试环境可能是
# (Although get_current_settings_from_file itself is not async, test env might be)
async def test_get_current_settings_from_file_success(
    settings_crud_instance: SettingsCRUD, mock_tmp_settings_file: Path
):
    """测试 get_current_settings_from_file 成功读取并解析JSON文件。"""
    expected_settings = {"app_name": "测试应用", "log_level": "DEBUG"}
    mock_tmp_settings_file.write_text(json.dumps(expected_settings), encoding="utf-8")

    current_settings = settings_crud_instance.get_current_settings_from_file()

    assert current_settings == expected_settings, "读取到的配置与预期不符。"


@pytest.mark.asyncio
async def test_get_current_settings_from_file_file_not_found(
    settings_crud_instance: SettingsCRUD, mock_tmp_settings_file: Path
):
    """测试 get_current_settings_from_file 在文件不存在时返回空字典并记录警告。"""
    # 确保文件不存在 (Ensure file does not exist)
    if mock_tmp_settings_file.exists():
        mock_tmp_settings_file.unlink()

    with patch.object(
        settings_crud_instance._settings_crud_logger, "warning"
    ) as mock_log_warning:
        current_settings = settings_crud_instance.get_current_settings_from_file()
        assert current_settings == {}, "文件不存在时应返回空字典。"
        mock_log_warning.assert_called_once()
        assert "未找到" in mock_log_warning.call_args[0][0], "应记录文件未找到的警告。"
        # (Should log file not found warning.)


@pytest.mark.asyncio
async def test_get_current_settings_from_file_corrupted_json(
    settings_crud_instance: SettingsCRUD, mock_tmp_settings_file: Path
):
    """测试 get_current_settings_from_file 在JSON文件损坏时返回空字典并记录错误。"""
    mock_tmp_settings_file.write_text(
        "{'bad_json':服务}", encoding="utf-8"
    )  # 无效JSON (Invalid JSON)

    with patch.object(
        settings_crud_instance._settings_crud_logger, "error"
    ) as mock_log_error:
        current_settings = settings_crud_instance.get_current_settings_from_file()
        assert current_settings == {}, "JSON损坏时应返回空字典。"
        mock_log_error.assert_called_once()
        assert "解码JSON失败" in mock_log_error.call_args[0][0], (
            "应记录JSON解码失败的错误。"
        )
        # (Should log JSON decode failure error.)


# endregion

# region update_settings_file_and_reload 测试 (update_settings_file_and_reload Tests)


@pytest.mark.asyncio
async def test_update_settings_file_and_reload_success(
    settings_crud_instance: SettingsCRUD, mock_tmp_settings_file: Path, mocker
):
    """测试 update_settings_file_and_reload 成功更新文件并触发配置重载。"""
    initial_settings = {"app_name": "旧应用名", "log_level": "INFO"}
    mock_tmp_settings_file.write_text(json.dumps(initial_settings), encoding="utf-8")

    update_payload = {"app_name": "新应用名", "token_expiry_hours": 48}
    # expected_written_settings = { # F841: 已确认未使用 (Confirmed unused)
    #     "app_name": "新应用名",
    #     "log_level": "INFO",
    #     "token_expiry_hours": 48,
    # }

    # 模拟 app.core.config.load_settings (或其调用的内部重载逻辑)
    # (Simulate app.core.config.load_settings (or its internally called reload logic))
    # SettingsCRUD 调用了全局的 load_settings 函数
    # (SettingsCRUD calls the global load_settings function)
    mock_load_settings = mocker.patch("app.core.config.load_settings")
    # 模拟它返回一个新的（模拟的）Settings对象，以确认重载效果
    # (Simulate it returns a new (mocked) Settings object to confirm reload effect)
    reloaded_settings_mock = MagicMock(spec=ActualSettings)
    reloaded_settings_mock.app_name = "新应用名"  # 确保模拟对象有更新的值
    # (Ensure mocked object has updated values)
    mock_load_settings.return_value = reloaded_settings_mock

    # 模拟全局的 settings 对象被正确更新 (Simulate global settings object is correctly updated)
    # 这是通过 app.crud.settings.settings = new_settings 实现的
    # (This is achieved by app.crud.settings.settings = new_settings)
    mocker.patch("app.crud.settings.settings", reloaded_settings_mock)

    await settings_crud_instance.update_settings_file_and_reload(update_payload)

    # 1. 检查文件内容是否被正确更新 (Check if file content was correctly updated)
    with open(mock_tmp_settings_file, "r", encoding="utf-8") as f:
        written_data = json.load(f)
    # 注意: SettingsCRUD 的实现是读取现有 -> 合并 -> 写入。
    # (Note: SettingsCRUD's implementation reads existing -> merges -> writes.)
    # 所以 "log_level": "INFO" 应该仍然存在。
    # (So "log_level": "INFO" should still be there.)
    assert written_data.get("app_name") == "新应用名", "配置文件中的 app_name 未更新。"
    assert written_data.get("token_expiry_hours") == 48, (
        "配置文件中的 token_expiry_hours 未更新。"
    )
    assert written_data.get("log_level") == "INFO", "配置文件中原有的 log_level 丢失。"

    # 2. 检查配置重载函数是否被调用 (Check if config reload function was called)
    mock_load_settings.assert_called_once()

    # 3. 检查模块内的 settings 实例是否被更新 (Check if settings instance within module was updated)
    #    这通过模拟 app.crud.settings.settings 来间接验证。
    #    (This is indirectly verified by mocking app.crud.settings.settings.)
    assert settings_crud_instance.settings.app_name == "新应用名", (
        "CRUD实例内部的settings对象未反映重载。"
    )


@pytest.mark.asyncio
async def test_update_settings_file_and_reload_io_error_on_write(
    settings_crud_instance: SettingsCRUD, mock_tmp_settings_file: Path, mocker
):
    """测试当写入设置文件发生IOError时的错误处理。"""
    initial_settings = {"app_name": "稳定应用"}
    mock_tmp_settings_file.write_text(json.dumps(initial_settings), encoding="utf-8")

    update_payload = {"log_level": "CRITICAL"}

    # 模拟 open 在写入时引发 IOError
    # (Simulate open raises IOError during write)
    mocked_open = mocker.patch("builtins.open", mock_open())
    # 让第二次调用 open (写入模式) 时引发异常
    # (Make the second call to open (write mode) raise an exception)
    mocked_open.side_effect = [
        mock_open(
            read_data=json.dumps(initial_settings)
        ).return_value,  # 第一次读取成功 (First read succeeds)
        IOError("磁盘已满测试 (Disk full test)"),  # 第二次写入失败 (Second write fails)
    ]

    # 确保重载函数不会被调用 (Ensure reload function is not called)
    mock_load_settings = mocker.patch("app.core.config.load_settings")

    with pytest.raises(IOError) as exc_info:
        await settings_crud_instance.update_settings_file_and_reload(update_payload)

    assert "磁盘已满测试" in str(exc_info.value), "IOError 未按预期引发或消息不符。"

    # 验证文件内容未被更改 (Verify file content was not changed)
    with open(mock_tmp_settings_file, "r", encoding="utf-8") as f:
        final_content = json.load(f)
    assert final_content == initial_settings, "发生IOError时，配置文件不应被修改。"

    mock_load_settings.assert_not_called(), "发生IOError时不应尝试重载配置。"


# endregion
