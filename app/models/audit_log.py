# -*- coding: utf-8 -*-
"""
审计日志相关的Pydantic模型模块。
(Pydantic Models Module for Audit Logs.)

此模块定义了用于表示审计日志条目的数据模型。
这些模型用于数据验证、序列化以及在应用内部传递审计日志信息。
(This module defines data models for representing audit log entries.
These models are used for data validation, serialization, and for passing
audit log information within the application.)
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    """
    审计日志条目的Pydantic模型。
    (Pydantic model for an audit log entry.)
    """

    event_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="事件的唯一ID (Unique ID for the event)",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="事件发生的时间戳 (UTC) (Timestamp of when the event occurred (UTC))",
    )
    actor_uid: Optional[str] = Field(
        None, description="执行操作的用户ID (UID of the user performing the action)"
    )
    actor_ip: Optional[str] = Field(
        None,
        description="执行操作用户的IP地址 (IP address of the user performing the action)",
    )
    action_type: str = Field(
        ...,
        description="操作类型 (例如: USER_LOGIN, ITEM_CREATE, CONFIG_UPDATE) (Type of action performed)",
    )
    target_resource_type: Optional[str] = Field(
        None,
        description="操作目标资源的类型 (例如: USER, PAPER, QUESTION_BANK) (Type of the target resource)",
    )
    target_resource_id: Optional[str] = Field(
        None, description="操作目标资源的ID (ID of the target resource)"
    )
    status: str = Field(
        ...,
        description="操作结果状态 (例如: SUCCESS, FAILURE) (Status of the action outcome)",
    )
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="与事件相关的其他详细信息 (Additional details related to the event)",
    )

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()  # Ensure datetime is serialized to ISO format
        }
    }


__all__ = ["AuditLogEntry"]
