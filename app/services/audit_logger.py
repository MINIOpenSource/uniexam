# -*- coding: utf-8 -*-
"""
审计日志服务模块。
(Audit Logging Service Module.)

此模块提供了一个服务类，用于记录应用中的重要操作和事件到审计日志文件。
审计日志以JSON格式记录，包含事件ID、时间戳、执行者、操作类型、目标资源、状态和详细信息。
(This module provides a service class for logging important actions and events
within the application to an audit log file. Audit logs are recorded in JSON format,
including event ID, timestamp, actor, action type, target resource, status, and details.)
"""

import asyncio
import logging
import os
from datetime import datetime  # Ensure datetime is imported for AuditLogEntry
from typing import Any, Dict, Optional

from app.core.config import settings  # Application settings
from app.models.audit_log_models import AuditLogEntry  # Audit log Pydantic model

# 审计日志文件的路径，从配置中读取
# (Path to the audit log file, read from configuration)
# Assuming settings.audit_log_file_path will be "data/logs/audit.log"
AUDIT_LOG_FILE_PATH = settings.audit_log_file_path


class AuditLoggerService:
    """
    审计日志服务类。
    (Audit Logging Service class.)

    负责初始化专用的审计日志记录器，并提供一个方法来记录结构化的审计事件。
    (Responsible for initializing a dedicated audit logger and providing a method
     to log structured audit events.)
    """

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        # Singleton pattern might be useful here if multiple instantiations are a concern,
        # but a global instance is also fine for this project structure.
        # For simplicity, we'll use a global instance approach rather than enforcing singleton here.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        初始化审计日志记录器。
        (Initializes the audit logger.)

        - 确保审计日志目录存在。
        - 设置一个名为 "audit_log" 的Python日志记录器。
        - 为此记录器配置一个文件处理器，指向 AUDIT_LOG_FILE_PATH。
        - 文件处理器的格式化器配置为直接输出原始JSON字符串。
        - 日志级别设置为 INFO。
        """
        # Ensure this runs only once for the global instance
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.logger_name = "audit_log"
        self.logger = logging.getLogger(self.logger_name)

        if not self.logger.handlers:  # Avoid adding multiple handlers if instantiated multiple times (though global instance should prevent this)
            # 确保日志目录存在 (Ensure log directory exists)
            log_dir = os.path.dirname(AUDIT_LOG_FILE_PATH)
            if log_dir and not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except OSError as e:
                    # Use a fallback logger or print if this critical setup fails
                    fallback_logger = logging.getLogger(__name__ + ".AuditLoggerSetup")
                    fallback_logger.error(
                        f"创建审计日志目录 '{log_dir}' 失败: {e}", exc_info=True
                    )
                    # Depending on policy, could raise error or continue without file logging for audit
                    # For now, it will try to add handler anyway, which might fail if dir doesn't exist

            handler = logging.FileHandler(AUDIT_LOG_FILE_PATH, encoding="utf-8")

            # 自定义格式化器，直接输出消息 (Custom formatter to output the message directly)
            # The message passed to logger will be the pre-formatted JSON string.
            class JsonFormatter(logging.Formatter):
                def format(self, record):
                    return record.getMessage()  # record.msg should be the JSON string

            handler.setFormatter(JsonFormatter())
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
            # Prevent audit logs from propagating to the root logger if it has other handlers (e.g. console)
            self.logger.propagate = False

        self._initialized = True

    async def log_event(
        self,
        action_type: str,
        status: str,
        actor_uid: Optional[str] = None,
        actor_ip: Optional[str] = None,
        target_resource_type: Optional[str] = None,
        target_resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        记录一个审计事件。
        (Logs an audit event.)

        参数 (Args):
            actor_uid (Optional[str]): 执行操作的用户ID。
            actor_ip (Optional[str]): 执行操作用户的IP地址。
            action_type (str): 操作类型。
            status (str): 操作结果状态 (例如："SUCCESS", "FAILURE")。
            target_resource_type (Optional[str]): 操作目标资源的类型。
            target_resource_id (Optional[str]): 操作目标资源的ID。
            details (Optional[Dict[str, Any]]): 与事件相关的其他详细信息。
        """
        try:
            log_entry = AuditLogEntry(
                timestamp=datetime.utcnow(),  # Generate timestamp at the moment of logging
                actor_uid=actor_uid,
                actor_ip=actor_ip,
                action_type=action_type,
                target_resource_type=target_resource_type,
                target_resource_id=target_resource_id,
                status=status,
                details=details,
            )

            # 使用 model_dump_json() 将Pydantic模型转换为JSON字符串
            # (Convert Pydantic model to JSON string using model_dump_json())
            log_json_string = log_entry.model_dump_json()

            # 使用配置好的审计日志记录器记录JSON字符串
            # (Log the JSON string using the configured audit logger)
            self.logger.info(log_json_string)

        except Exception as e:
            # 如果审计日志本身失败，记录到应用主日志或标准错误输出
            # (If audit logging itself fails, log to the main app logger or stderr)
            app_fallback_logger = logging.getLogger(__name__ + ".AuditLoggingError")
            app_fallback_logger.error(
                f"记录审计事件失败 (Failed to log audit event): {e}", exc_info=True
            )
            app_fallback_logger.error(
                f"失败的审计事件数据 (Failed audit event data): action_type={action_type}, status={status}, actor_uid={actor_uid}"
            )


# 创建审计日志服务的全局实例
# (Create a global instance of the audit logging service)
audit_logger_service = AuditLoggerService()

__all__ = ["audit_logger_service", "AuditLoggerService"]
