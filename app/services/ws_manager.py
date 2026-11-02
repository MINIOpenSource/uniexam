from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional
import uuid
from fastapi import WebSocket


@dataclass
class DeviceConnection:
    websocket: WebSocket
    user_id: str
    username: str
    role: str
    device_id: str
    device_name: str
    ip_address: str
    connected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    active_paper_id: Optional[str] = None
    paper_difficulty: Optional[str] = None
    current_question_index: int = 0
    answered_count: int = 0
    total_questions: int = 0
    page_mode: str = "user_center"
    exam_state: str = "idle"
    window_focused: bool = True
    visibility_state: str = "visible"
    pointer_in_viewport: bool = True
    mouse_x: Optional[float] = None
    mouse_y: Optional[float] = None
    viewport_w: Optional[int] = None
    viewport_h: Optional[int] = None
    hovered_zone: str = "page_blank"
    focus_loss_count: int = 0
    leave_viewport_count: int = 0
    dom_purged: bool = False
    shield_master_on: bool = False
    security_alert_count: int = 0
    last_security_alert: Optional[str] = None
    last_mouse_active_at: Optional[str] = None
    last_active_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "uid": self.username,
            "role": self.role,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "ip_address": self.ip_address,
            "connected_at": self.connected_at,
            "active_paper_id": self.active_paper_id,
            "paper_difficulty": self.paper_difficulty,
            "current_question_index": self.current_question_index,
            "answered_count": self.answered_count,
            "total_questions": self.total_questions,
            "page_mode": self.page_mode,
            "exam_state": self.exam_state,
            "window_focused": self.window_focused,
            "visibility_state": self.visibility_state,
            "pointer_in_viewport": self.pointer_in_viewport,
            "mouse_x": self.mouse_x,
            "mouse_y": self.mouse_y,
            "viewport_w": self.viewport_w,
            "viewport_h": self.viewport_h,
            "hovered_zone": self.hovered_zone,
            "focus_loss_count": self.focus_loss_count,
            "leave_viewport_count": self.leave_viewport_count,
            "dom_purged": self.dom_purged,
            "shield_master_on": self.shield_master_on,
            "security_alert_count": self.security_alert_count,
            "last_security_alert": self.last_security_alert,
            "last_mouse_active_at": self.last_mouse_active_at,
            "last_active_at": self.last_active_at,
        }


class WebSocketManager:
    def __init__(self) -> None:
        # username -> { device_id -> DeviceConnection }
        self._user_connections: Dict[str, Dict[str, DeviceConnection]] = {}
        # Ring buffer of recent live telemetry / security / exam events for Admin Panel
        self._live_events: Deque[Dict[str, Any]] = deque(maxlen=200)

    @staticmethod
    def _is_admin_conn(conn: DeviceConnection) -> bool:
        return (
            str(conn.role).lower() in ("admin", "manager")
            or conn.username == "admin"
        )

    async def register(self, conn: DeviceConnection) -> None:
        user_bucket = self._user_connections.setdefault(conn.username, {})
        old_conn = user_bucket.get(conn.device_id)
        if old_conn and old_conn.websocket is not conn.websocket:
            try:
                await old_conn.websocket.close(code=4000)
            except Exception:
                pass
        user_bucket[conn.device_id] = conn
        await self.broadcast_presence(
            conn.username, exclude_device_id=conn.device_id
        )
        await self.record_live_event(
            category="connection",
            severity="info",
            username=conn.username,
            device_id=conn.device_id,
            device_name=conn.device_name,
            ip_address=conn.ip_address,
            message="前端已建立实时 WebSocket 连接",
        )

    async def unregister(
        self,
        username: str,
        device_id: str,
        websocket: Optional[WebSocket] = None,
    ) -> None:
        user_bucket = self._user_connections.get(username)
        if not user_bucket:
            return
        existing = user_bucket.get(device_id)
        removed_conn: Optional[DeviceConnection] = None
        if existing and (websocket is None or existing.websocket is websocket):
            removed_conn = user_bucket.pop(device_id, None)
        if not user_bucket:
            self._user_connections.pop(username, None)
        else:
            await self.broadcast_presence(username)
        if removed_conn:
            await self.record_live_event(
                category="connection",
                severity="info",
                username=removed_conn.username,
                device_id=removed_conn.device_id,
                device_name=removed_conn.device_name,
                ip_address=removed_conn.ip_address,
                message="前端已断开 WebSocket 连接",
                paper_id=removed_conn.active_paper_id,
                question_index=removed_conn.current_question_index,
            )

    def get_user_devices(self, username: str) -> List[Dict[str, Any]]:
        user_bucket = self._user_connections.get(username, {})
        return [c.to_public_dict() for c in user_bucket.values()]

    def get_all_connections(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for user_bucket in self._user_connections.values():
            for conn in user_bucket.values():
                items.append(conn.to_public_dict())
        # Sort active exam takers first, then unfocused/alerted, then by last_active_at desc
        items.sort(
            key=lambda x: (
                0 if x.get("page_mode") == "exam_active_direct" or x.get("active_paper_id") else 1,
                0 if (not x.get("window_focused", True) or not x.get("pointer_in_viewport", True) or x.get("dom_purged", False)) else 1,
                -(datetime.fromisoformat(x["last_active_at"]).timestamp() if x.get("last_active_at") else 0),
            )
        )
        return items

    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(self._live_events)[:limit]

    async def record_live_event(
        self,
        category: str,
        severity: str,
        username: str,
        device_id: str,
        device_name: str,
        ip_address: str,
        message: str,
        paper_id: Optional[str] = None,
        question_index: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        evt: Dict[str, Any] = {
            "id": str(uuid.uuid4())[:12],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "severity": severity,  # "info" | "warning" | "danger" | "success"
            "uid": username,
            "device_id": device_id,
            "device_name": device_name,
            "ip_address": ip_address,
            "message": message,
            "paper_id": paper_id,
            "question_index": question_index,
        }
        if extra:
            evt.update(extra)
        self._live_events.appendleft(evt)
        await self.broadcast_to_admins(
            {
                "type": "admin_live_event",
                "event": evt,
                "connections": self.get_all_connections(),
                "timestamp": evt["timestamp"],
            }
        )
        return evt

    async def broadcast_admin_live_state(self) -> None:
        await self.broadcast_to_admins(
            {
                "type": "admin_live_state",
                "connections": self.get_all_connections(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_connection(
        self, username: str, device_id: str
    ) -> Optional[DeviceConnection]:
        return self._user_connections.get(username, {}).get(device_id)

    def update_device_state(
        self,
        username: str,
        device_id: str,
        active_paper_id: Optional[str] = None,
        current_question_index: Optional[int] = None,
        answered_count: Optional[int] = None,
        total_questions: Optional[int] = None,
        paper_difficulty: Optional[str] = None,
        page_mode: Optional[str] = None,
        exam_state: Optional[str] = None,
        clear_paper: bool = False,
    ) -> None:
        user_bucket = self._user_connections.get(username, {})
        conn = user_bucket.get(device_id)
        if not conn:
            return
        conn.last_active_at = datetime.now(timezone.utc).isoformat()
        if clear_paper:
            conn.active_paper_id = None
            conn.paper_difficulty = None
            conn.current_question_index = 0
            conn.answered_count = 0
            conn.total_questions = 0
        else:
            if active_paper_id is not None:
                conn.active_paper_id = active_paper_id
            if paper_difficulty is not None:
                conn.paper_difficulty = paper_difficulty
            if current_question_index is not None:
                conn.current_question_index = current_question_index
            if answered_count is not None:
                conn.answered_count = answered_count
            if total_questions is not None:
                conn.total_questions = total_questions
        if page_mode is not None:
            conn.page_mode = page_mode
        if exam_state is not None:
            conn.exam_state = exam_state

    async def send_to_device(
        self, username: str, device_id: str, message: Dict[str, Any]
    ) -> bool:
        user_bucket = self._user_connections.get(username, {})
        conn = user_bucket.get(device_id)
        if not conn:
            return False
        try:
            await conn.websocket.send_json(message)
            return True
        except Exception:
            await self.unregister(username, device_id, conn.websocket)
            return False

    async def broadcast_to_user(
        self,
        username: str,
        message: Dict[str, Any],
        exclude_device_id: Optional[str] = None,
    ) -> None:
        user_bucket = self._user_connections.get(username, {})
        if not user_bucket:
            return
        stale_ids: List[str] = []
        for dev_id, conn in list(user_bucket.items()):
            if exclude_device_id and dev_id == exclude_device_id:
                continue
            try:
                await conn.websocket.send_json(message)
            except Exception:
                stale_ids.append(dev_id)
        for dev_id in stale_ids:
            user_bucket.pop(dev_id, None)
        if not user_bucket:
            self._user_connections.pop(username, None)

    async def broadcast_presence(
        self, username: str, exclude_device_id: Optional[str] = None
    ) -> None:
        devices = self.get_user_devices(username)
        await self.broadcast_to_user(
            username,
            {
                "type": "presence_update",
                "uid": username,
                "devices": devices,
                "device_count": len(devices),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            exclude_device_id=exclude_device_id,
        )

    async def broadcast_to_admins(self, message: Dict[str, Any]) -> None:
        for username, user_bucket in list(self._user_connections.items()):
            for dev_id, conn in list(user_bucket.items()):
                if self._is_admin_conn(conn):
                    try:
                        await conn.websocket.send_json(message)
                    except Exception:
                        pass

    async def kick_device(
        self,
        username: str,
        target_device_id: str,
        reason: str = "Disconnected by another device",
    ) -> bool:
        user_bucket = self._user_connections.get(username, {})
        conn = user_bucket.get(target_device_id)
        if not conn:
            return False
        try:
            await conn.websocket.send_json(
                {"type": "kicked", "reason": reason, "device_id": target_device_id}
            )
            await conn.websocket.close(code=4002)
        except Exception:
            pass
        user_bucket.pop(target_device_id, None)
        if not user_bucket:
            self._user_connections.pop(username, None)
        else:
            await self.broadcast_presence(username)
        await self.record_live_event(
            category="security",
            severity="warning",
            username=username,
            device_id=target_device_id,
            device_name=conn.device_name,
            ip_address=conn.ip_address,
            message=f"设备连接已被强制断开: {reason}",
            paper_id=conn.active_paper_id,
        )
        return True

    async def disconnect_all_for_user(
        self, username: str, reason: str = "Session revoked"
    ) -> None:
        user_bucket = self._user_connections.pop(username, {})
        for conn in list(user_bucket.values()):
            try:
                await conn.websocket.send_json({"type": "kicked", "reason": reason})
                await conn.websocket.close(code=4001)
            except Exception:
                pass
        if user_bucket:
            await self.broadcast_admin_live_state()


ws_manager = WebSocketManager()
