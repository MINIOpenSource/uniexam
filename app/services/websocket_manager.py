# -*- coding: utf-8 -*-
"""
WebSocket 连接管理模块。
(WebSocket Connection Management Module.)

此模块提供了一个 `WebSocketManager` 类，用于管理活跃的 WebSocket 连接，
并支持向所有连接的客户端广播消息。主要用于实时通知功能，例如通知管理员。
(This module provides a `WebSocketManager` class for managing active WebSocket connections
and supports broadcasting messages to all connected clients. It is primarily intended for
real-time notification features, such as notifying administrators.)
"""

import asyncio
import logging
from typing import (
    Any,
    Dict,
    Set,
)  # List for potential future use with multiple rooms

from fastapi import WebSocket

# 获取本模块的日志记录器实例
# (Get logger instance for this module)
_websocket_manager_logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    管理 WebSocket 连接的类。
    (Class for managing WebSocket connections.)

    提供连接、断开连接以及广播消息的功能。
    (Provides functionalities for connecting, disconnecting, and broadcasting messages.)
    """

    def __init__(self):
        """
        初始化 WebSocketManager。
        (Initializes the WebSocketManager.)

        `active_connections`: 一个集合，存储所有当前活跃的 WebSocket 连接。
                              (A set storing all currently active WebSocket connections.)
        `lock`: 一个异步锁，用于在并发操作中保护 `active_connections`。
                (An asyncio.Lock to protect `active_connections` during concurrent operations.)
        """
        self.active_connections: Set[WebSocket] = set()
        self.lock = asyncio.Lock()
        _websocket_manager_logger.info(
            "WebSocket 管理器已初始化。 (WebSocketManager initialized.)"
        )

    async def connect(self, websocket: WebSocket) -> None:
        """
        处理新的 WebSocket 连接。
        (Handles a new WebSocket connection.)

        将新的 WebSocket 对象添加到活跃连接集合中。
        (Adds the new WebSocket object to the set of active connections.)

        参数 (Args):
            websocket (WebSocket): 要添加的 FastAPI WebSocket 对象。
                                   (The FastAPI WebSocket object to add.)
        """
        await (
            websocket.accept()
        )  # 接受 WebSocket 连接 (Accept the WebSocket connection)
        async with self.lock:
            self.active_connections.add(websocket)
        # 获取客户端信息用于日志记录 (Get client info for logging)
        client_host = websocket.client.host if websocket.client else "未知主机"
        client_port = websocket.client.port if websocket.client else "未知端口"
        _websocket_manager_logger.info(
            f"WebSocket 已连接: {client_host}:{client_port}。当前总连接数: {len(self.active_connections)}。"
            f"(WebSocket connected: {client_host}:{client_port}. Total connections: {len(self.active_connections)}.)"
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        处理 WebSocket 断开连接。
        (Handles a WebSocket disconnection.)

        从活跃连接集合中移除指定的 WebSocket 对象。
        (Removes the specified WebSocket object from the set of active connections.)

        参数 (Args):
            websocket (WebSocket): 要移除的 FastAPI WebSocket 对象。
                                   (The FastAPI WebSocket object to remove.)
        """
        async with self.lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        # 获取客户端信息用于日志记录 (Get client info for logging)
        client_host = websocket.client.host if websocket.client else "未知主机"
        client_port = websocket.client.port if websocket.client else "未知端口"
        _websocket_manager_logger.info(
            f"WebSocket 已断开: {client_host}:{client_port}。剩余连接数: {len(self.active_connections)}。"
            f"(WebSocket disconnected: {client_host}:{client_port}. Remaining connections: {len(self.active_connections)}.)"
        )
        # WebSocket 对象通常由 FastAPI 在断开后自行关闭，此处无需显式调用 websocket.close()
        # (The WebSocket object is typically closed by FastAPI itself after disconnection,
        #  no explicit call to websocket.close() is needed here.)

    async def broadcast_message(self, message: Dict[str, Any]) -> None:
        """
        向所有当前连接的 WebSocket 客户端广播一条JSON消息。
        (Broadcasts a JSON message to all currently connected WebSocket clients.)

        如果发送消息给某个客户端时发生异常（例如连接已关闭），则会安全地移除该客户端。
        (If an exception occurs while sending a message to a client (e.g., connection closed),
         that client will be safely removed.)

        参数 (Args):
            message (Dict[str, Any]): 要广播的JSON可序列化字典消息。
                                      (The JSON-serializable dictionary message to broadcast.)
        """
        # 创建一个当前连接的副本进行迭代，以允许在广播过程中安全地修改原始集合
        # (Create a copy of current connections for iteration to allow safe modification
        #  of the original set during broadcasting.)

        # 使用锁来确保在复制和迭代期间连接列表的完整性
        # (Use lock to ensure integrity of connection list during copy and iteration)
        disconnected_websockets: Set[WebSocket] = set()

        async with self.lock:
            # 收集所有仍然活跃的连接进行广播
            # (Collect all still active connections for broadcasting)
            # This is important because a connection might have been closed right before acquiring the lock
            connections_to_broadcast = list(self.active_connections)

        if not connections_to_broadcast:
            _websocket_manager_logger.info(
                "广播消息：无活跃连接，消息未发送。 (Broadcast message: No active connections, message not sent.)"
            )
            return

        _websocket_manager_logger.debug(
            f"准备向 {len(connections_to_broadcast)} 个连接广播消息: {message}"
        )

        for websocket in connections_to_broadcast:
            try:
                await websocket.send_json(message)
            except Exception as e:  # WebSocketException, ConnectionClosed, etc.
                # 客户端可能已断开连接 (Client might have disconnected)
                client_host = websocket.client.host if websocket.client else "未知主机"
                client_port = websocket.client.port if websocket.client else "未知端口"
                _websocket_manager_logger.warning(
                    f"广播消息给 {client_host}:{client_port} 失败: {e}。将标记此连接为待移除。"
                    f"(Failed to broadcast message to {client_host}:{client_port}: {e}. Marking connection for removal.)"
                )
                disconnected_websockets.add(websocket)

        # 如果在广播过程中有连接失败，则从主列表中移除它们
        # (If any connections failed during broadcast, remove them from the main list)
        if disconnected_websockets:
            async with self.lock:
                for ws_to_remove in disconnected_websockets:
                    if (
                        ws_to_remove in self.active_connections
                    ):  # 再次检查，以防在两次获取锁之间状态改变
                        self.active_connections.remove(ws_to_remove)
            _websocket_manager_logger.info(
                f"已从活跃连接中移除 {len(disconnected_websockets)} 个失败的WebSocket连接。"
            )


# 创建 WebSocketManager 的全局实例
# (Create a global instance of WebSocketManager)
websocket_manager = WebSocketManager()

__all__ = ["websocket_manager", "WebSocketManager"]
