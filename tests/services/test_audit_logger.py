# -*- coding: utf-8 -*-
"""
app.services.audit_logger.AuditLoggerService 类的单元测试。
(Unit tests for the app.services.audit_logger.AuditLoggerService class.)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import (  # patch from unittest.mock is fine with pytest
    MagicMock,
)
from uuid import UUID  # For checking event_id format

import pytest

from app.core.config import Settings as AppSettings  # For mocking settings

# AUDIT_LOG_FILE_PATH as ACTUAL_AUDIT_LOG_FILE_PATH # Not needed if we patch settings
# 模块被测试 (Module under test)
from app.services.audit_logger import AuditLoggerService

# region Fixtures (测试固件)


@pytest.fixture
def mock_settings_for_audit(mocker, tmp_path: Path) -> AppSettings:
    """提供一个模拟的Settings对象，其中audit_log_file_path指向临时路径。"""
    temp_log_file = tmp_path / "test_audit.log"
    mock_settings = MagicMock(spec=AppSettings)
    mock_settings.audit_log_file_path = str(temp_log_file)
    mocker.patch("app.services.audit_logger.settings", mock_settings)
    return mock_settings


# endregion

# region Initialization Tests (初始化测试)


def test_audit_logger_service_initialization(
    mocker, mock_settings_for_audit: AppSettings, tmp_path: Path
):
    """
    测试 AuditLoggerService 初始化过程。
    验证日志目录创建、日志记录器获取和处理器配置。
    """
    mock_os_makedirs = mocker.patch("os.makedirs")

    mock_logger_instance = MagicMock(spec=logging.Logger)
    mock_logger_instance.handlers = []
    mock_getLogger = mocker.patch(
        "logging.getLogger", return_value=mock_logger_instance
    )

    mock_file_handler_constructor = mocker.patch("logging.FileHandler")

    from app.services.audit_logger import (
        audit_logger_service,  # Import the global instance
    )

    # Reset _initialized flag and handlers on the global instance to test __init__
    if hasattr(audit_logger_service, "_initialized"):
        delattr(audit_logger_service, "_initialized")
    if (
        hasattr(audit_logger_service, "logger")
        and audit_logger_service.logger is not None
    ):
        audit_logger_service.logger.handlers = []  # Clear handlers to allow re-adding

    # Patch AUDIT_LOG_FILE_PATH at the module level where AuditLoggerService reads it
    mocker.patch(
        "app.services.audit_logger.AUDIT_LOG_FILE_PATH",
        str(mock_settings_for_audit.audit_log_file_path),
    )

    # Create a new instance for this test to ensure __init__ is called with mocks
    test_service_instance = AuditLoggerService()
    assert (
        test_service_instance is not None
    )  # Explicitly use the instance to satisfy F841

    log_dir = Path(mock_settings_for_audit.audit_log_file_path).parent
    mock_os_makedirs.assert_called_once_with(log_dir, exist_ok=True)

    # getLogger will be called for "audit_log" and potentially for fallback loggers.
    # We are primarily interested in "audit_log".
    found_audit_log_call = False
    for call_args in mock_getLogger.call_args_list:
        if call_args[0][0] == "audit_log":
            found_audit_log_call = True
            break
    assert found_audit_log_call, 'logging.getLogger("audit_log") was not called.'

    assert mock_logger_instance.addHandler.called, "未向日志记录器添加处理器。"
    assert mock_logger_instance.setLevel.called_with(logging.INFO), (
        "日志记录器的级别设置不正确。"
    )
    mock_file_handler_constructor.assert_called_once_with(
        str(mock_settings_for_audit.audit_log_file_path), encoding="utf-8"
    )
    assert mock_logger_instance.propagate is False, (
        "日志记录器的 propagate 应设为 False。"
    )


# endregion

# region log_event Tests (log_event 测试)


@pytest.mark.asyncio
async def test_log_event_success(mocker, mock_settings_for_audit: AppSettings):
    """测试 log_event 成功记录一个标准的审计事件。"""

    mock_audit_logger_info = MagicMock()
    mock_logger = MagicMock(spec=logging.Logger)
    mock_logger.info = mock_audit_logger_info

    mocker.patch("logging.getLogger", return_value=mock_logger)
    mocker.patch(
        "app.services.audit_logger.AUDIT_LOG_FILE_PATH",
        str(mock_settings_for_audit.audit_log_file_path),
    )

    from app.services.audit_logger import audit_logger_service

    original_logger = audit_logger_service.logger
    audit_logger_service.logger = mock_logger

    actor_uid_val = "user123"
    actor_ip_val = "192.168.1.100"
    action_type_val = "ITEM_CREATE"
    status_val = "SUCCESS"
    target_resource_type_val = "ITEM"
    target_resource_id_val = "item_abc"
    details_val = {"name": "My New Item", "value": 42}

    await audit_logger_service.log_event(
        actor_uid=actor_uid_val,
        actor_ip=actor_ip_val,
        action_type=action_type_val,
        status=status_val,
        target_resource_type=target_resource_type_val,
        target_resource_id=target_resource_id_val,
        details=details_val,
    )

    mock_audit_logger_info.assert_called_once()
    logged_json_str = mock_audit_logger_info.call_args[0][0]
    logged_data = json.loads(logged_json_str)

    assert "event_id" in logged_data
    assert "timestamp" in logged_data
    assert UUID(logged_data["event_id"], version=4).hex == logged_data["event_id"]
    log_time = datetime.fromisoformat(logged_data["timestamp"].replace("Z", "+00:00"))
    assert (datetime.now(timezone.utc) - log_time).total_seconds() < 5, (
        "时间戳不是最近的UTC时间。"
    )

    assert logged_data["actor_uid"] == actor_uid_val
    assert logged_data["actor_ip"] == actor_ip_val
    assert logged_data["action_type"] == action_type_val
    assert logged_data["status"] == status_val
    assert logged_data["target_resource_type"] == target_resource_type_val
    assert logged_data["target_resource_id"] == target_resource_id_val
    assert logged_data["details"] == details_val

    audit_logger_service.logger = original_logger


@pytest.mark.asyncio
async def test_log_event_with_minimal_fields(
    mocker, mock_settings_for_audit: AppSettings
):
    """测试 log_event 只使用必需字段记录事件。"""
    mock_audit_logger_info = MagicMock()
    mock_logger = MagicMock(spec=logging.Logger)
    mock_logger.info = mock_audit_logger_info
    mocker.patch("logging.getLogger", return_value=mock_logger)
    mocker.patch(
        "app.services.audit_logger.AUDIT_LOG_FILE_PATH",
        str(mock_settings_for_audit.audit_log_file_path),
    )

    from app.services.audit_logger import audit_logger_service

    original_logger = audit_logger_service.logger
    audit_logger_service.logger = mock_logger

    action_type_val = "SYSTEM_HEALTH_CHECK"
    status_val = "SUCCESS"

    await audit_logger_service.log_event(action_type=action_type_val, status=status_val)

    mock_audit_logger_info.assert_called_once()
    logged_json_str = mock_audit_logger_info.call_args[0][0]
    logged_data = json.loads(logged_json_str)

    assert logged_data["action_type"] == action_type_val
    assert logged_data["status"] == status_val
    assert logged_data["actor_uid"] is None
    assert logged_data["actor_ip"] is None
    assert logged_data["target_resource_type"] is None
    assert logged_data["target_resource_id"] is None
    assert logged_data["details"] is None

    audit_logger_service.logger = original_logger


@pytest.mark.asyncio
async def test_log_event_logging_failure_fallback(
    mocker, mock_settings_for_audit: AppSettings
):
    """测试当主审计日志记录失败时，是否调用了备用日志记录器。"""
    mock_audit_logger_info = MagicMock(
        side_effect=IOError("模拟磁盘写入错误 (Simulated disk write error)")
    )
    primary_mock_logger = MagicMock(spec=logging.Logger)
    primary_mock_logger.info = mock_audit_logger_info

    mock_fallback_logger_error = MagicMock()
    fallback_mock_logger = MagicMock(spec=logging.Logger)
    fallback_mock_logger.error = mock_fallback_logger_error

    def getLogger_side_effect(name):
        if name == "audit_log":
            return primary_mock_logger
        elif name == "app.services.audit_logger.AuditLoggingError":
            return fallback_mock_logger
        return MagicMock()

    mocker.patch("logging.getLogger", side_effect=getLogger_side_effect)
    mocker.patch(
        "app.services.audit_logger.AUDIT_LOG_FILE_PATH",
        str(mock_settings_for_audit.audit_log_file_path),
    )

    from app.services.audit_logger import audit_logger_service

    audit_logger_service.logger = primary_mock_logger

    await audit_logger_service.log_event(action_type="TEST_ACTION", status="FAILURE")

    mock_audit_logger_info.assert_called_once()
    mock_fallback_logger_error.assert_called()

    fallback_call_args = mock_fallback_logger_error.call_args[0]
    assert "记录审计事件失败" in fallback_call_args[0], "备用日志消息不符合预期。"
    assert "模拟磁盘写入错误" in str(fallback_call_args[1]), (
        "原始异常未传递给备用日志。"
    )


# endregion
