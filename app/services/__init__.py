# -*- coding: utf-8 -*-
"""
app.services 包初始化文件。

此包用于存放应用的服务层逻辑。服务层通常包含协调不同 CRUD 操作、
处理业务逻辑以及与外部服务交互等功能。

目前此包为空，未来可以根据需求添加具体服务模块。
"""

# from . import some_service # Example placeholder
from .websocket_manager import (
    WebSocketManager,
    websocket_manager,
)  # 导入新的WebSocket管理器

__all__ = [
    # "some_service", # Example placeholder
    # "SomeServiceClass", # Example placeholder
    "WebSocketManager",
    "websocket_manager",
]

# Example of how to structure when services are added:
#
# from . import some_service
# from .some_service import SomeServiceClass
#
# __all__ = [
#     "some_service",
#     "SomeServiceClass",
# ]
