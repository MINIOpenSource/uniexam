# -*- coding: utf-8 -*-
"""
WebSocket API 路由模块。
(WebSocket API Routing Module.)

此模块定义了所有与 WebSocket 通信相关的API端点。
例如，用于实时监控、通知等功能。
(This module defines all API endpoints related to WebSocket communication,
for example, for real-time monitoring, notifications, etc.)
"""

import logging

from fastapi import (
    APIRouter,
    Depends,
    WebSocket,
    WebSocketDisconnect,
)

from .core.security import require_admin  # 用于 WebSocket 端点的管理权限验证
from .services.websocket_manager import websocket_manager

# (For admin permission verification on WebSocket endpoints)

# 获取本模块的日志记录器实例
# (Get logger instance for this module)
_ws_logger = logging.getLogger(__name__)

# 创建 WebSocket 路由实例
# (Create WebSocket router instance)
# 注意: FastAPI 对 APIRouter 上的 `dependencies` 用于 WebSocket 的行为可能有限。
#       通常，WebSocket的认证在连接建立时通过查询参数或头部信息在端点函数内部处理。
#       此处添加 `Depends(require_admin)` 是为了声明意图，实际执行可能需要调整。
# (Note: FastAPI's behavior for `dependencies` on APIRouter with WebSockets might be limited.
#  Typically, WebSocket authentication is handled within the endpoint function during connection
#  establishment using query parameters or headers. Adding `Depends(require_admin)` here
#  declares intent; actual execution might require adjustments.)
ws_router = APIRouter(
    tags=["WebSocket接口 (WebSocket Interface)"],
    dependencies=[Depends(require_admin)],  # 尝试对整个路由应用管理员认证
    # (Attempt to apply admin authentication to the entire router)
)


@ws_router.websocket("/ws/exam_monitor")
async def websocket_exam_monitor(websocket: WebSocket):
    """
    考试监控 WebSocket 端点。
    (Exam Monitoring WebSocket Endpoint.)

    管理员客户端可以通过此端点连接，以接收实时的考试监控信息（例如，考生提交试卷事件）。
    (Administrator clients can connect via this endpoint to receive real-time exam monitoring
     information (e.g., examinee submission events).)

    认证 (Authentication):
        连接时需要在查询参数中提供有效的管理员Token (例如: `/ws/exam_monitor?token=YOUR_ADMIN_TOKEN`)。
        (A valid admin token must be provided as a query parameter upon connection
         (e.g., `/ws/exam_monitor?token=YOUR_ADMIN_TOKEN`).)
    """
    # 实际的管理员身份验证已由 `Depends(require_admin)` 在 APIRouter 级别（尝试）处理。
    # 如果该机制对 WebSocket 不完全适用，认证逻辑需要移到此处，
    # 例如通过 `token: Optional[str] = Query(None)` 获取token，然后调用 `validate_token_and_get_user_info`。
    # (Actual admin authentication is (attempted) by `Depends(require_admin)` at the APIRouter level.
    #  If this mechanism is not fully applicable to WebSockets, authentication logic needs to be moved here,
    #  e.g., by getting the token via `token: Optional[str] = Query(None)` and then calling
    #  `validate_token_and_get_user_info`.)

    # 假设 `require_admin` 依赖项如果失败会直接拒绝连接或 `websocket.scope['user']` 会被填充。
    # (Assuming the `require_admin` dependency would reject the connection if failed,
    #  or `websocket.scope['user']` would be populated.)

    # 从 scope 中获取认证信息 (这是 FastAPI 处理依赖注入的一种方式，但对 WebSocket 可能不同)
    # (Getting auth info from scope - this is one way FastAPI handles DI, but might differ for WebSockets)
    # admin_user_info = websocket.scope.get("user_info_from_token", None) # 假设依赖注入会填充这个
    # actor_uid = admin_user_info.get("user_uid", "unknown_ws_admin") if admin_user_info else "unknown_ws_admin"
    # ^^^ 上述方法依赖于 `require_admin` 如何将信息传递给 WebSocket scope，
    #     这通常不直接发生。`require_admin` 会在 HTTP 升级请求阶段起作用。

    client_host = websocket.client.host if websocket.client else "未知主机"
    client_port = websocket.client.port if websocket.client else "未知端口"

    # 由于 `require_admin` 会在连接尝试时验证，若失败则不会执行到这里。
    # 若成功，我们可以认为连接的是已认证的管理员。
    # (Since `require_admin` validates upon connection attempt, if it fails, execution won't reach here.
    #  If successful, we can assume the connected client is an authenticated admin.)
    _ws_logger.info(
        f"管理员客户端 {client_host}:{client_port} 已连接到考试监控 WebSocket。"
        f"(Admin client {client_host}:{client_port} connected to exam monitoring WebSocket.)"
    )

    await websocket_manager.connect(websocket)
    try:
        while True:
            # 管理员客户端通常只接收由服务器推送的消息。
            # (Admin clients typically only receive messages pushed by the server.)
            # 此处 `receive_text` / `receive_json` 主要用于保持连接活性或处理客户端发来的控制指令（如果设计有）。
            # (Here, `receive_text` / `receive_json` is mainly for keeping the connection alive
            #  or processing control commands from the client (if designed).)
            data = await websocket.receive_text()
            _ws_logger.debug(
                f"从管理员客户端 {client_host}:{client_port} 收到监控 WebSocket 文本消息: {data}"
                f"(Received text message from admin client {client_host}:{client_port} on monitoring WebSocket: {data})"
            )
            # 示例：如果客户端发送特定指令
            # (Example: if client sends a specific command)
            # if data == "PING":
            #     await websocket.send_text("PONG")
            # 一般管理员监控端点不需要处理来自客户端的太多常规消息。
            # (Generally, admin monitoring endpoints don't need to process many regular messages from clients.)

    except WebSocketDisconnect:
        _ws_logger.info(
            f"管理员客户端 {client_host}:{client_port} 已从考试监控 WebSocket 断开。"
            f"(Admin client {client_host}:{client_port} disconnected from exam monitoring WebSocket.)"
        )
    except Exception as e:
        # 记录任何其他在 WebSocket 通信期间发生的异常
        # (Log any other exceptions occurring during WebSocket communication)
        _ws_logger.error(
            f"考试监控 WebSocket ({client_host}:{client_port}) 发生错误: {e}. "
            f"英文详情 (English details): (Exam monitoring WebSocket ({client_host}:{client_port}) encountered an error: {e})",
            exc_info=True,
        )
    finally:
        # 确保无论因何原因循环结束，连接都会从管理器中断开
        # (Ensure the connection is removed from the manager regardless of why the loop ended)
        await websocket_manager.disconnect(websocket)


__all__ = ["ws_router"]
