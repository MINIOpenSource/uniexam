# -*- coding: utf-8 -*-
"""
app.services.websocket_manager.WebSocketManager 类的单元测试。
(Unit tests for the app.services.websocket_manager.WebSocketManager class.)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket  # 用于类型提示和模拟 (For type hinting and mocking)

# 模块被测试 (Module under test)
from app.services.websocket_manager import WebSocketManager

# region Fixtures (测试固件)


@pytest.fixture
def websocket_manager_instance() -> WebSocketManager:
    """提供一个全新的 WebSocketManager 实例，用于每个测试。"""
    # (Provides a fresh WebSocketManager instance for each test.)
    # 清理可能由其他测试遗留的锁 (如果 WebSocketManager 使用了类级别或全局锁字典)
    # (Clean up locks possibly left over from other tests (if WebSocketManager used class-level or global lock dicts))
    # 当前 WebSocketManager 的锁是实例成员，所以每次创建新实例都是干净的。
    # (Currently, WebSocketManager's lock is an instance member, so each new instance is clean.)
    return WebSocketManager()


def create_mock_websocket(
    mocker, client_host="127.0.0.1", client_port=12345
) -> MagicMock:
    """
    创建一个模拟的 FastAPI WebSocket 对象。
    (Creates a mocked FastAPI WebSocket object.)
    """
    mock_ws = MagicMock(spec=WebSocket)
    mock_ws.accept = (
        AsyncMock()
    )  # connect 方法会调用 accept (connect method calls accept)
    mock_ws.send_json = AsyncMock()
    mock_ws.send_text = (
        AsyncMock()
    )  # 以防万一有其他类型的发送 (Just in case other send types are used)
    mock_ws.receive_text = AsyncMock()
    mock_ws.receive_json = AsyncMock()

    # 模拟 client 属性 (Simulate client attribute)
    mock_ws.client = MagicMock()
    mock_ws.client.host = client_host
    mock_ws.client.port = client_port
    return mock_ws


# endregion

# region connect 和 disconnect 测试 (connect and disconnect Tests)


@pytest.mark.asyncio
async def test_connect_adds_websocket(
    websocket_manager_instance: WebSocketManager, mocker
):
    """测试 connect 方法是否能将 WebSocket 添加到 active_connections。"""
    mock_ws = create_mock_websocket(mocker)

    initial_connection_count = len(websocket_manager_instance.active_connections)
    await websocket_manager_instance.connect(mock_ws)

    assert mock_ws in websocket_manager_instance.active_connections, (
        "WebSocket 未被添加到 active_connections。"
    )
    assert (
        len(websocket_manager_instance.active_connections)
        == initial_connection_count + 1
    ), "连接数未正确增加。"
    mock_ws.accept.assert_called_once(), "websocket.accept() 未被调用。"


@pytest.mark.asyncio
async def test_disconnect_removes_websocket(
    websocket_manager_instance: WebSocketManager, mocker
):
    """测试 disconnect 方法是否能从 active_connections 移除 WebSocket。"""
    mock_ws1 = create_mock_websocket(mocker, client_port=10001)
    mock_ws2 = create_mock_websocket(mocker, client_port=10002)

    # 先连接两个 (Connect two first)
    await websocket_manager_instance.connect(mock_ws1)
    await websocket_manager_instance.connect(mock_ws2)
    assert len(websocket_manager_instance.active_connections) == 2, "初始连接数不为2。"

    # 断开其中一个 (Disconnect one of them)
    await websocket_manager_instance.disconnect(mock_ws1)

    assert mock_ws1 not in websocket_manager_instance.active_connections, (
        "mock_ws1 未从 active_connections 移除。"
    )
    assert mock_ws2 in websocket_manager_instance.active_connections, (
        "mock_ws2 不应被移除。"
    )
    assert len(websocket_manager_instance.active_connections) == 1, (
        "断开连接后，剩余连接数不正确。"
    )

    # 再次断开同一个，不应发生错误 (Disconnect the same one again, should not error)
    await websocket_manager_instance.disconnect(mock_ws1)
    assert len(websocket_manager_instance.active_connections) == 1, (
        "重复断开不应改变连接数。"
    )


# endregion

# region broadcast_message 测试 (broadcast_message Tests)


@pytest.mark.asyncio
async def test_broadcast_message_sends_to_all_connected(
    websocket_manager_instance: WebSocketManager, mocker
):
    """测试 broadcast_message 能向所有连接的客户端发送消息。"""
    mock_ws1 = create_mock_websocket(mocker, client_port=20001)
    mock_ws2 = create_mock_websocket(mocker, client_port=20002)

    await websocket_manager_instance.connect(mock_ws1)
    await websocket_manager_instance.connect(mock_ws2)

    test_message = {"event_type": "GREETING", "content": "大家好！"}
    await websocket_manager_instance.broadcast_message(test_message)

    mock_ws1.send_json.assert_called_once_with(test_message)
    mock_ws2.send_json.assert_called_once_with(test_message)


@pytest.mark.asyncio
async def test_broadcast_message_handles_send_exception_and_disconnects(
    websocket_manager_instance: WebSocketManager, mocker
):
    """测试 broadcast_message 在发送异常时能处理并断开失败的连接。"""
    mock_ws_ok = create_mock_websocket(mocker, client_host="ok_host", client_port=30001)
    mock_ws_fail = create_mock_websocket(
        mocker, client_host="fail_host", client_port=30002
    )

    # mock_ws_ok.send_json = AsyncMock() # 已在 create_mock_websocket 中设置 (Already set in create_mock_websocket)
    mock_ws_fail.send_json.side_effect = Exception(
        "模拟发送失败 (Simulated send failure)"
    )

    await websocket_manager_instance.connect(mock_ws_ok)
    await websocket_manager_instance.connect(mock_ws_fail)

    assert len(websocket_manager_instance.active_connections) == 2, "初始连接数不为2。"

    test_message = {"event_type": "IMPORTANT_UPDATE", "data": "一些数据"}
    await websocket_manager_instance.broadcast_message(test_message)

    mock_ws_ok.send_json.assert_called_once_with(test_message)
    mock_ws_fail.send_json.assert_called_once_with(
        test_message
    )  # 仍然尝试发送 (Still attempts to send)

    # 检查连接状态 (Check connection status)
    # 加锁以安全地检查 active_connections (Lock to safely check active_connections)
    async with websocket_manager_instance.lock:
        assert mock_ws_ok in websocket_manager_instance.active_connections, (
            "正常的WebSocket不应被移除。"
        )
        assert mock_ws_fail not in websocket_manager_instance.active_connections, (
            "发送失败的WebSocket应被移除。"
        )
    assert len(websocket_manager_instance.active_connections) == 1, (
        "处理异常后连接数不正确。"
    )


@pytest.mark.asyncio
async def test_broadcast_message_empty_connections(
    websocket_manager_instance: WebSocketManager, mocker
):
    """测试当没有活跃连接时 broadcast_message 的行为。"""
    # 确保 active_connections 为空 (Ensure active_connections is empty)
    assert len(websocket_manager_instance.active_connections) == 0

    # 为 logging.info 打补丁以检查日志输出
    # (Patch logging.info to check log output)
    mock_logger_info = mocker.patch.object(
        websocket_manager_instance._websocket_manager_logger, "info"
    )
    # 注意: 这里是实例的logger，或者模块级logger `_websocket_manager_logger`
    # (Note: This is instance's logger, or module-level logger `_websocket_manager_logger`)

    test_message = {"event_type": "PING", "content": "有人吗？"}
    await websocket_manager_instance.broadcast_message(test_message)

    # 确认没有尝试发送任何消息 (Confirm no attempt to send any message)
    # (这是间接的，因为没有mock的send_json被调用)
    # (This is indirect, as no mocked send_json would be called)

    # 确认记录了“无活跃连接”的日志 (Confirm "No active connections" log was recorded)
    assert any(
        "无活跃连接" in call_args[0][0] for call_args in mock_logger_info.call_args_list
    ), "当无连接时，应记录'无活跃连接'信息。"


# endregion
