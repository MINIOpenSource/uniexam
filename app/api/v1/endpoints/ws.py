import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.v1.endpoints.legacy_compat import _compute_pass_status, _paper_meta
from app.db.base import AsyncSessionLocal
from app.db.models import Paper, PaperQuestion, PaperStatus
from app.services.auth import AuthService
from app.services.grading import grading_service
from app.services.paper_hash import paper_issuance_service
from app.services.ws_manager import DeviceConnection, ws_manager

router = APIRouter()


def _extract_selected_texts_from_paper(paper: Paper):
    selected_texts = []
    for pq in paper.paper_questions:
        ans = pq.user_answer
        if isinstance(ans, dict):
            txt = ans.get("selected_text")
            if txt is None:
                canon_id = ans.get("selected_option_id")
                options = (pq.question.content or {}).get("options", {})
                if canon_id and isinstance(options, dict):
                    txt = options.get(str(canon_id))
            selected_texts.append(txt)
        else:
            selected_texts.append(None)
    return selected_texts


def _extract_selected_canon_ids_from_paper(paper: Paper):
    canon_ids = []
    for pq in paper.paper_questions:
        ans = pq.user_answer
        if isinstance(ans, dict):
            canon_ids.append(ans.get("selected_option_id"))
        else:
            canon_ids.append(None)
    return canon_ids


def _extract_ws_token_and_subprotocol(websocket: WebSocket) -> tuple[Optional[str], Optional[str]]:
    # 1. Standard Authorization or X-Access-Token header (e.g. non-browser WS clients)
    auth_header = websocket.headers.get("authorization") or websocket.headers.get("x-access-token")
    if auth_header:
        val = auth_header.strip()
        if val.lower().startswith("bearer "):
            val = val.split(" ", 1)[1].strip()
        if val:
            return val, None

    # 2. Browser WebSocket Sec-WebSocket-Protocol header: ["uniexam-v1", "bearer.<token>"]
    proto_header = websocket.headers.get("sec-websocket-protocol")
    if proto_header:
        parts = [p.strip() for p in proto_header.split(",") if p.strip()]
        selected_subproto = parts[0] if parts else None
        for p in parts:
            if p.startswith("bearer."):
                tok = p[len("bearer."):].strip()
                if tok:
                    return tok, selected_subproto or p
            elif p != "uniexam-v1" and len(p) >= 32:
                return p, selected_subproto or p
    return None, None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    device_id: Optional[str] = Query(default=None),
    device_name: Optional[str] = Query(default="Web Client"),
):
    token, accepted_subprotocol = _extract_ws_token_and_subprotocol(websocket)
    if not token:
        await websocket.close(code=4001)
        return

    async with AsyncSessionLocal() as session:
        auth_service = AuthService(session)
        user = await auth_service.get_user_by_token(token)
        if not user or not user.is_active:
            await websocket.close(code=4001)
            return
        user_id = user.id
        username = user.username
        user_role = user.role.value if hasattr(user.role, "value") else str(user.role)

    await websocket.accept(subprotocol=accepted_subprotocol)

    dev_id = device_id or str(uuid.uuid4())
    dev_name = (device_name or "Web Client")[:64]
    client_ip = websocket.client.host if websocket.client else "127.0.0.1"

    conn = DeviceConnection(
        websocket=websocket,
        user_id=user_id,
        username=username,
        role=user_role,
        device_id=dev_id,
        device_name=dev_name,
        ip_address=client_ip,
    )
    await websocket.send_json(
        {
            "type": "connected",
            "uid": username,
            "device_id": dev_id,
            "device_name": dev_name,
            "devices": ws_manager.get_user_devices(username) + [conn.to_public_dict()],
            "server_time_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    await ws_manager.register(conn)

    # If the connecting client is an admin/manager, immediately send full live state + recent events
    is_admin = str(user_role).lower() in ("admin", "manager") or username == "admin"
    if is_admin:
        await websocket.send_json(
            {
                "type": "admin_live_state",
                "connections": ws_manager.get_all_connections(),
                "events": ws_manager.get_recent_events(100),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                conn.last_active_at = datetime.now(timezone.utc).isoformat()
                await websocket.send_json(
                    {
                        "type": "pong",
                        "timestamp": conn.last_active_at,
                    }
                )

            elif msg_type == "client_telemetry":
                now_iso = datetime.now(timezone.utc).isoformat()
                conn.last_active_at = now_iso

                prev_focused = conn.window_focused
                prev_visibility = conn.visibility_state
                prev_in_viewport = conn.pointer_in_viewport
                prev_dom_purged = conn.dom_purged

                if "window_focused" in data:
                    conn.window_focused = bool(data["window_focused"])
                if "visibility_state" in data and data["visibility_state"]:
                    conn.visibility_state = str(data["visibility_state"])[:16]
                if "pointer_in_viewport" in data:
                    conn.pointer_in_viewport = bool(data["pointer_in_viewport"])
                if "mouse_x" in data:
                    mx = data["mouse_x"]
                    conn.mouse_x = round(float(mx), 4) if mx is not None else None
                    if mx is not None:
                        conn.last_mouse_active_at = now_iso
                if "mouse_y" in data:
                    my = data["mouse_y"]
                    conn.mouse_y = round(float(my), 4) if my is not None else None
                if "viewport_w" in data and data["viewport_w"] is not None:
                    conn.viewport_w = int(data["viewport_w"])
                if "viewport_h" in data and data["viewport_h"] is not None:
                    conn.viewport_h = int(data["viewport_h"])
                if "hovered_zone" in data and data["hovered_zone"]:
                    conn.hovered_zone = str(data["hovered_zone"])[:48]
                if "page_mode" in data and data["page_mode"]:
                    conn.page_mode = str(data["page_mode"])[:32]
                if "exam_state" in data and data["exam_state"]:
                    conn.exam_state = str(data["exam_state"])[:32]
                if "active_paper_id" in data:
                    conn.active_paper_id = data["active_paper_id"] or None
                if "paper_difficulty" in data:
                    conn.paper_difficulty = data["paper_difficulty"] or None
                if "current_question_index" in data and data["current_question_index"] is not None:
                    conn.current_question_index = int(data["current_question_index"])
                if "answered_count" in data and data["answered_count"] is not None:
                    conn.answered_count = int(data["answered_count"])
                if "total_questions" in data and data["total_questions"] is not None:
                    conn.total_questions = int(data["total_questions"])
                if "focus_loss_count" in data and data["focus_loss_count"] is not None:
                    conn.focus_loss_count = int(data["focus_loss_count"])
                if "leave_viewport_count" in data and data["leave_viewport_count"] is not None:
                    conn.leave_viewport_count = int(data["leave_viewport_count"])
                if "dom_purged" in data:
                    conn.dom_purged = bool(data["dom_purged"])
                if "shield_master_on" in data:
                    conn.shield_master_on = bool(data["shield_master_on"])
                if "security_alert_count" in data and data["security_alert_count"] is not None:
                    conn.security_alert_count = int(data["security_alert_count"])
                if "last_security_alert" in data and data["last_security_alert"]:
                    conn.last_security_alert = str(data["last_security_alert"])[:160]

                # Emit structured live events on meaningful transitions
                event_emitted = False
                security_event_msg = data.get("security_event")
                if security_event_msg:
                    await ws_manager.record_live_event(
                        category="security",
                        severity="danger",
                        username=username,
                        device_id=dev_id,
                        device_name=dev_name,
                        ip_address=client_ip,
                        message=str(security_event_msg)[:180],
                        paper_id=conn.active_paper_id,
                        question_index=conn.current_question_index,
                    )
                    event_emitted = True
                elif not prev_dom_purged and conn.dom_purged:
                    await ws_manager.record_live_event(
                        category="security",
                        severity="danger",
                        username=username,
                        device_id=dev_id,
                        device_name=dev_name,
                        ip_address=client_ip,
                        message="触发 F12 / 调试探针：已静默清空 DOM 题干并切换至 CSSOM 渲染",
                        paper_id=conn.active_paper_id,
                        question_index=conn.current_question_index,
                    )
                    event_emitted = True

                if prev_visibility == "visible" and conn.visibility_state != "visible":
                    await ws_manager.record_live_event(
                        category="focus",
                        severity="warning",
                        username=username,
                        device_id=dev_id,
                        device_name=dev_name,
                        ip_address=client_ip,
                        message="页面标签页切至后台 (visibility=hidden)",
                        paper_id=conn.active_paper_id,
                        question_index=conn.current_question_index,
                    )
                    event_emitted = True
                elif prev_focused and not conn.window_focused:
                    await ws_manager.record_live_event(
                        category="focus",
                        severity="warning",
                        username=username,
                        device_id=dev_id,
                        device_name=dev_name,
                        ip_address=client_ip,
                        message="浏览器窗口失去焦点 (window.blur)",
                        paper_id=conn.active_paper_id,
                        question_index=conn.current_question_index,
                    )
                    event_emitted = True
                elif (not prev_focused and conn.window_focused) or (
                    prev_visibility != "visible" and conn.visibility_state == "visible"
                ):
                    await ws_manager.record_live_event(
                        category="focus",
                        severity="info",
                        username=username,
                        device_id=dev_id,
                        device_name=dev_name,
                        ip_address=client_ip,
                        message="浏览器窗口恢复焦点 (window.focus)",
                        paper_id=conn.active_paper_id,
                        question_index=conn.current_question_index,
                    )
                    event_emitted = True

                if prev_in_viewport and not conn.pointer_in_viewport and conn.window_focused:
                    await ws_manager.record_live_event(
                        category="pointer",
                        severity="warning",
                        username=username,
                        device_id=dev_id,
                        device_name=dev_name,
                        ip_address=client_ip,
                        message="鼠标指针移出浏览器视口边界 (pointerleave)",
                        paper_id=conn.active_paper_id,
                        question_index=conn.current_question_index,
                    )
                    event_emitted = True

                if not event_emitted:
                    await ws_manager.broadcast_admin_live_state()

            elif msg_type == "admin_request_live_state":
                if is_admin:
                    await websocket.send_json(
                        {
                            "type": "admin_live_state",
                            "connections": ws_manager.get_all_connections(),
                            "events": ws_manager.get_recent_events(100),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )

            elif msg_type == "admin_kick_device":
                if is_admin:
                    target_uid = data.get("target_uid")
                    target_dev_id = data.get("target_device_id")
                    reason = data.get("reason") or f"已被管理员 ({username}) 强制断开连接"
                    if target_uid and target_dev_id:
                        await ws_manager.kick_device(target_uid, target_dev_id, reason=reason)
                        await ws_manager.broadcast_admin_live_state()

            elif msg_type == "join_paper":
                paper_id = data.get("paper_id")
                paper_hash = data.get("paper_hash")
                q_idx = int(data.get("current_question_index") or 0)
                if not paper_id:
                    continue

                async with AsyncSessionLocal() as session:
                    stmt = (
                        select(Paper)
                        .options(
                            selectinload(Paper.paper_questions).selectinload(
                                PaperQuestion.question
                            )
                        )
                        .where(Paper.id == paper_id)
                    )
                    paper = (await session.execute(stmt)).scalars().first()
                    if paper and paper.user_id == user_id:
                        selected_texts = _extract_selected_texts_from_paper(paper)
                        selected_canon_ids = _extract_selected_canon_ids_from_paper(paper)
                        selected_uuids = paper_issuance_service.resolve_canon_ids_for_hash(
                            paper_hash, selected_canon_ids
                        )
                        finished_count = sum(1 for t in selected_texts if t is not None)
                        total_q = len(paper.paper_questions)
                        total = paper.total_score or total_q or 1.0
                        pct = (
                            round(((paper.score or 0.0) / total) * 100.0, 2)
                            if paper.status != PaperStatus.PENDING and total > 0
                            else None
                        )
                        meta = _paper_meta.get(paper.id, {})
                        ws_manager.update_device_state(
                            username,
                            dev_id,
                            active_paper_id=paper_id,
                            current_question_index=q_idx,
                            answered_count=finished_count,
                            total_questions=total_q,
                            paper_difficulty=meta.get("difficulty"),
                            page_mode="exam_active_direct",
                            exam_state="taking",
                        )
                        await ws_manager.broadcast_presence(username)
                        await ws_manager.record_live_event(
                            category="exam",
                            severity="info",
                            username=username,
                            device_id=dev_id,
                            device_name=dev_name,
                            ip_address=client_ip,
                            message=f"进入试卷作答 ({paper_id[:8]}... · 第 {q_idx + 1}/{total_q} 题)",
                            paper_id=paper_id,
                            question_index=q_idx,
                        )
                        await websocket.send_json(
                            {
                                "type": "paper_state",
                                "paper_id": paper.id,
                                "status": paper.status.value
                                if hasattr(paper.status, "value")
                                else str(paper.status),
                                "selected_texts": selected_texts,
                                "selected_uuids": selected_uuids,
                                "finished_count": finished_count,
                                "total_count": total_q,
                                "score": int(round(pct)) if pct is not None else None,
                                "score_percentage": pct,
                                "pass_status": _compute_pass_status(paper),
                                "passcode": meta.get("passcode"),
                            }
                        )

            elif msg_type == "leave_paper":
                prev_paper = conn.active_paper_id
                ws_manager.update_device_state(
                    username,
                    dev_id,
                    clear_paper=True,
                    page_mode="user_center",
                    exam_state="idle",
                )
                await ws_manager.broadcast_presence(username)
                if prev_paper:
                    await ws_manager.record_live_event(
                        category="exam",
                        severity="info",
                        username=username,
                        device_id=dev_id,
                        device_name=dev_name,
                        ip_address=client_ip,
                        message=f"离开试卷作答视图 ({prev_paper[:8]}...)",
                        paper_id=prev_paper,
                    )
                else:
                    await ws_manager.broadcast_admin_live_state()

            elif msg_type == "cursor_move":
                paper_id = data.get("paper_id")
                q_idx = int(data.get("current_question_index") or 0)
                ws_manager.update_device_state(
                    username,
                    dev_id,
                    active_paper_id=paper_id,
                    current_question_index=q_idx,
                )
                await ws_manager.broadcast_presence(username)
                await ws_manager.broadcast_to_user(
                    username,
                    {
                        "type": "cursor_synced",
                        "paper_id": paper_id,
                        "current_question_index": q_idx,
                        "source_device_id": dev_id,
                        "source_device_name": dev_name,
                    },
                    exclude_device_id=dev_id,
                )
                await ws_manager.record_live_event(
                    category="exam",
                    severity="info",
                    username=username,
                    device_id=dev_id,
                    device_name=dev_name,
                    ip_address=client_ip,
                    message=f"切换至第 {q_idx + 1} 题",
                    paper_id=paper_id,
                    question_index=q_idx,
                )

            elif msg_type == "sync_progress":
                paper_id = data.get("paper_id")
                submitted_paper = data.get("paper")
                submitted_result = data.get("result") or []
                submitted_hash = data.get("paper_hash")
                q_idx = data.get("current_question_index")

                if not paper_id:
                    await websocket.send_json(
                        {"type": "sync_error", "detail": "MISSING_PAPER_ID"}
                    )
                    continue

                async with AsyncSessionLocal() as session:
                    stmt = (
                        select(Paper)
                        .options(
                            selectinload(Paper.paper_questions).selectinload(
                                PaperQuestion.question
                            )
                        )
                        .where(Paper.id == paper_id)
                    )
                    paper = (await session.execute(stmt)).scalars().first()
                    if not paper or paper.user_id != user_id:
                        await websocket.send_json(
                            {
                                "type": "sync_error",
                                "paper_id": paper_id,
                                "detail": "NOT_FOUND",
                            }
                        )
                        continue
                    if paper.status != PaperStatus.PENDING:
                        await websocket.send_json(
                            {
                                "type": "sync_error",
                                "paper_id": paper_id,
                                "detail": "ALREADY_GRADED",
                            }
                        )
                        continue

                    try:
                        resolved_answers, selected_texts = (
                            await paper_issuance_service.verify_and_resolve_legacy_submission(
                                paper=paper,
                                submitted_paper=submitted_paper,
                                submitted_result=submitted_result,
                                submitted_hash=submitted_hash,
                                db=session,
                            )
                        )
                    except ValueError as e:
                        await websocket.send_json(
                            {
                                "type": "sync_error",
                                "paper_id": paper_id,
                                "detail": str(e),
                            }
                        )
                        continue

                    for idx, pq in enumerate(paper.paper_questions):
                        pq.user_answer = resolved_answers[idx]

                    await session.commit()

                    now_iso = datetime.now(timezone.utc).isoformat()
                    meta = _paper_meta.setdefault(paper.id, {})
                    meta["last_update_time_utc"] = now_iso
                    meta["last_update_ip"] = client_ip
                    finished_count = sum(
                        1 for a in resolved_answers if a is not None
                    )
                    total_count = len(paper.paper_questions)

                ws_manager.update_device_state(
                    username,
                    dev_id,
                    active_paper_id=paper_id,
                    current_question_index=int(q_idx) if q_idx is not None else conn.current_question_index,
                    answered_count=finished_count,
                    total_questions=total_count,
                )
                await ws_manager.broadcast_presence(username)

                await websocket.send_json(
                    {
                        "type": "progress_saved",
                        "status_code": "PROGRESS_SAVED",
                        "paper_id": paper_id,
                        "last_update_time_utc": now_iso,
                        "finished_count": finished_count,
                    }
                )

                await ws_manager.broadcast_to_user(
                    username,
                    {
                        "type": "progress_synced",
                        "paper_id": paper_id,
                        "selected_texts": selected_texts,
                        "current_question_index": q_idx,
                        "finished_count": finished_count,
                        "total_count": total_count,
                        "source_device_id": dev_id,
                        "source_device_name": dev_name,
                        "last_update_time_utc": now_iso,
                    },
                    exclude_device_id=dev_id,
                )
                await ws_manager.broadcast_to_admins(
                    {
                        "type": "admin_paper_updated",
                        "paper_id": paper_id,
                        "action": "progress",
                        "finished_count": finished_count,
                        "total_count": total_count,
                    }
                )
                await ws_manager.record_live_event(
                    category="exam",
                    severity="info",
                    username=username,
                    device_id=dev_id,
                    device_name=dev_name,
                    ip_address=client_ip,
                    message=f"实时保存答题进度 ({finished_count}/{total_count})",
                    paper_id=paper_id,
                    question_index=conn.current_question_index,
                )

            elif msg_type == "finish_exam":
                paper_id = data.get("paper_id")
                submitted_paper = data.get("paper")
                submitted_result = data.get("result") or []
                submitted_hash = data.get("paper_hash")

                if not paper_id:
                    await websocket.send_json(
                        {"type": "sync_error", "detail": "MISSING_PAPER_ID"}
                    )
                    continue

                async with AsyncSessionLocal() as session:
                    stmt = (
                        select(Paper)
                        .options(
                            selectinload(Paper.paper_questions).selectinload(
                                PaperQuestion.question
                            )
                        )
                        .where(Paper.id == paper_id)
                    )
                    paper = (await session.execute(stmt)).scalars().first()
                    if not paper or paper.user_id != user_id:
                        await websocket.send_json(
                            {
                                "type": "sync_error",
                                "paper_id": paper_id,
                                "detail": "NOT_FOUND",
                            }
                        )
                        continue
                    if paper.status != PaperStatus.PENDING:
                        await websocket.send_json(
                            {
                                "type": "sync_error",
                                "paper_id": paper_id,
                                "detail": "ALREADY_GRADED",
                            }
                        )
                        continue

                    try:
                        resolved_answers, selected_texts = (
                            await paper_issuance_service.verify_and_resolve_legacy_submission(
                                paper=paper,
                                submitted_paper=submitted_paper,
                                submitted_result=submitted_result,
                                submitted_hash=submitted_hash,
                                db=session,
                            )
                        )
                    except ValueError as e:
                        await websocket.send_json(
                            {
                                "type": "sync_error",
                                "paper_id": paper_id,
                                "detail": str(e),
                            }
                        )
                        continue

                    total_awarded = 0.0
                    for idx, pq in enumerate(paper.paper_questions):
                        ans_dict = resolved_answers[idx]
                        if ans_dict is not None:
                            pq.user_answer = ans_dict
                            mult = grading_service.grade_question(
                                pq.question, ans_dict
                            )
                            pq.score_awarded = mult * pq.max_score
                            pq.is_correct = mult == 1.0
                            total_awarded += pq.score_awarded
                        else:
                            pq.user_answer = None
                            pq.score_awarded = 0.0
                            pq.is_correct = False

                    paper.score = total_awarded
                    paper.status = PaperStatus.GRADED
                    paper.submitted_at = datetime.now(timezone.utc)
                    await session.commit()

                    total_possible = (
                        paper.total_score or len(paper.paper_questions) or 1.0
                    )
                    pct = (
                        round((total_awarded / total_possible) * 100.0, 2)
                        if total_possible > 0
                        else 0.0
                    )
                    passed = pct >= 60.0
                    pass_status = "PASSED" if passed else "FAILED"
                    passcode = secrets.token_hex(4).upper() if passed else None

                    meta = _paper_meta.setdefault(paper.id, {})
                    meta["pass_status"] = pass_status
                    meta["passcode"] = passcode
                    meta["submission_ip"] = client_ip
                    meta["last_update_time_utc"] = paper.submitted_at.isoformat()
                    submitted_iso = paper.submitted_at.isoformat()

                ws_manager.update_device_state(
                    username,
                    dev_id,
                    exam_state="success" if passed else "failed",
                )

                finish_msg = {
                    "type": "exam_finished",
                    "paper_id": paper_id,
                    "status_code": pass_status,
                    "message": "Exam graded successfully",
                    "passcode": passcode,
                    "score": int(round(pct)),
                    "score_percentage": pct,
                    "pending_manual_grading_count": 0,
                    "submission_time_utc": submitted_iso,
                    "source_device_id": dev_id,
                }
                await ws_manager.broadcast_to_user(username, finish_msg)
                await ws_manager.broadcast_to_admins(
                    {
                        "type": "admin_paper_updated",
                        "paper_id": paper_id,
                        "action": "finished",
                        "pass_status": pass_status,
                        "score": int(round(pct)),
                    }
                )
                await ws_manager.record_live_event(
                    category="exam",
                    severity="success" if passed else "warning",
                    username=username,
                    device_id=dev_id,
                    device_name=dev_name,
                    ip_address=client_ip,
                    message=f"已交卷判分：{pass_status} ({int(round(pct))} 分)",
                    paper_id=paper_id,
                )

            elif msg_type == "resolve_sync":
                paper_id = data.get("paper_id")
                paper_hash = data.get("paper_hash")
                if not paper_id or not paper_hash:
                    continue
                async with AsyncSessionLocal() as session:
                    stmt = (
                        select(Paper)
                        .options(
                            selectinload(Paper.paper_questions).selectinload(
                                PaperQuestion.question
                            )
                        )
                        .where(Paper.id == paper_id)
                    )
                    paper = (await session.execute(stmt)).scalars().first()
                    if paper and paper.user_id == user_id:
                        selected_canon_ids = _extract_selected_canon_ids_from_paper(paper)
                        selected_uuids = paper_issuance_service.resolve_canon_ids_for_hash(
                            paper_hash, selected_canon_ids
                        )
                        if selected_uuids is not None:
                            await websocket.send_json(
                                {
                                    "type": "resolved_sync",
                                    "paper_id": paper.id,
                                    "selected_uuids": selected_uuids,
                                }
                            )

            elif msg_type == "kick_device":
                target_id = data.get("target_device_id")
                if target_id and target_id != dev_id:
                    await ws_manager.kick_device(
                        username,
                        target_id,
                        reason=f"已被设备 ({dev_name}) 断开连接",
                    )

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_manager.unregister(username, dev_id, websocket)
