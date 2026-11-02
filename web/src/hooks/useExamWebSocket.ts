"use client";

import { useEffect, useRef, useState, useCallback } from 'react';
import type {
  ConnectedDevice,
  AdminLiveEvent,
  WsConnectionStatus,
  PaperSubmissionPayload,
  GradingResultResponse,
} from '@/types/exam';

export interface ProgressSyncedEvent {
  type: 'progress_synced';
  paper_id: string;
  selected_texts: (string | null)[];
  selected_canon_ids?: (string | null)[];
  current_question_index?: number | null;
  finished_count: number;
  total_count: number;
  source_device_id?: string | null;
  source_device_name?: string;
  last_update_time_utc?: string;
}

export interface PaperStateEvent {
  type: 'paper_state';
  paper_id: string;
  status: string;
  selected_texts: (string | null)[];
  selected_uuids?: (string | null)[] | null;
  finished_count: number;
  total_count: number;
  score?: number | null;
  score_percentage?: number | null;
  pass_status?: string | null;
  passcode?: string | null;
}

export interface ResolvedSyncEvent {
  type: 'resolved_sync';
  paper_id: string;
  selected_uuids: (string | null)[];
}

export interface CursorSyncedEvent {
  type: 'cursor_synced';
  paper_id: string;
  current_question_index: number;
  source_device_id: string;
  source_device_name: string;
}

export interface ExamFinishedEvent extends GradingResultResponse {
  type: 'exam_finished';
  paper_id: string;
  source_device_id?: string | null;
  submission_time_utc?: string;
}

export interface ExamCreatedEvent {
  type: 'exam_created';
  paper_id: string;
  difficulty: string;
  question_count: number;
  source_device_id?: string | null;
}

export interface TelemetryRuntimeContext {
  pageMode?: string;
  examState?: string;
  paperId?: string | null;
  paperDifficulty?: string | null;
  currentQuestionIndex?: number;
  answeredCount?: number;
  totalQuestions?: number;
  domPurged?: boolean;
  shieldMasterOn?: boolean;
  securityAlertCount?: number;
  lastSecurityAlert?: string | null;
}

export interface UseExamWebSocketOptions {
  token?: string | null;
  telemetryContext?: TelemetryRuntimeContext;
  onPaperState?: (event: PaperStateEvent) => void;
  onProgressSynced?: (event: ProgressSyncedEvent) => void;
  onResolvedSync?: (event: ResolvedSyncEvent) => void;
  onProgressSaved?: (event: {
    paper_id: string;
    last_update_time_utc: string;
    finished_count: number;
  }) => void;
  onCursorSynced?: (event: CursorSyncedEvent) => void;
  onExamFinished?: (event: ExamFinishedEvent) => void;
  onExamCreated?: (event: ExamCreatedEvent) => void;
  onAdminPaperUpdated?: (event: { paper_id: string; action: string }) => void;
  onSyncError?: (event: { paper_id?: string; detail: string }) => void;
  onKicked?: (event: { reason: string }) => void;
}

function detectDeviceName(shortId: string): string {
  if (typeof navigator === 'undefined') return `Web #${shortId}`;
  const ua = navigator.userAgent;
  let browser = 'Browser';
  if (ua.includes('Edg/')) browser = 'Edge';
  else if (ua.includes('Chrome/')) browser = 'Chrome';
  else if (ua.includes('Firefox/')) browser = 'Firefox';
  else if (ua.includes('Safari/')) browser = 'Safari';

  let os = 'Device';
  if (ua.includes('Windows')) os = 'Windows';
  else if (ua.includes('Mac OS')) os = 'macOS';
  else if (ua.includes('Android')) os = 'Android';
  else if (ua.includes('iPhone') || ua.includes('iPad')) os = 'iOS';
  else if (ua.includes('Linux')) os = 'Linux';

  return `${browser} (${os}) #${shortId}`;
}

function getOrCreateDeviceIdentity(): { deviceId: string; deviceName: string } {
  if (typeof window === 'undefined') {
    return { deviceId: 'ssr-device', deviceName: 'SSR Client' };
  }
  const storageKey = 'uniexam_ws_device_id';
  let devId = sessionStorage.getItem(storageKey);
  if (!devId) {
    devId =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `dev-${Math.random().toString(36).slice(2, 10)}-${Date.now()}`;
    sessionStorage.setItem(storageKey, devId);
  }
  const shortId = devId.slice(0, 4).toUpperCase();
  return {
    deviceId: devId,
    deviceName: detectDeviceName(shortId),
  };
}

function resolveWsUrl(deviceId: string, deviceName: string): string {
  const params = new URLSearchParams({
    device_id: deviceId,
    device_name: deviceName,
  });

  if (process.env.NEXT_PUBLIC_WS_URL) {
    const base = process.env.NEXT_PUBLIC_WS_URL.replace(/\/$/, '');
    return `${base}?${params.toString()}`;
  }

  if (typeof window !== 'undefined') {
    const isSecure = window.location.protocol === 'https:';
    const wsProto = isSecure ? 'wss:' : 'ws:';
    const hostname = window.location.hostname || '127.0.0.1';
    const backendPort = process.env.NEXT_PUBLIC_BACKEND_PORT || '8000';
    return `${wsProto}//${hostname}:${backendPort}/ws?${params.toString()}`;
  }

  return `ws://127.0.0.1:8000/ws?${params.toString()}`;
}

function resolveHoveredZoneFromPointerEvent(e: PointerEvent | MouseEvent): string {
  const target = e.target as HTMLElement | null;
  if (!target || typeof target.closest !== 'function') {
    return e.clientY < 52 ? 'header' : 'page_blank';
  }
  const zoneEl = target.closest('[data-ue-zone]') as HTMLElement | null;
  if (zoneEl) {
    const z = zoneEl.getAttribute('data-ue-zone') || 'page_blank';
    if (z === 'question_options') {
      const rect = zoneEl.getBoundingClientRect();
      if (rect.height > 0) {
        const relY = Math.max(0, Math.min(0.999, (e.clientY - rect.top) / rect.height));
        const slotIdx = Math.floor(relY * 4);
        const labels = ['option_A', 'option_B', 'option_C', 'option_D'];
        return labels[slotIdx] || 'question_options';
      }
    }
    return z;
  }
  if (e.clientY < 52) return 'header';
  return 'page_blank';
}

export function useExamWebSocket(options: UseExamWebSocketOptions) {
  const { token, telemetryContext } = options;
  const callbacksRef = useRef(options);
  callbacksRef.current = options;

  const telemetryContextRef = useRef<TelemetryRuntimeContext>(telemetryContext || {});
  telemetryContextRef.current = telemetryContext || {};

  const [status, setStatus] = useState<WsConnectionStatus>('disconnected');
  const [deviceId, setDeviceId] = useState<string>('');
  const [deviceName, setDeviceName] = useState<string>('');
  const [devices, setDevices] = useState<ConnectedDevice[]>([]);
  const [adminLiveConnections, setAdminLiveConnections] = useState<ConnectedDevice[]>([]);
  const [adminLiveEvents, setAdminLiveEvents] = useState<AdminLiveEvent[]>([]);
  const [lastSyncInfo, setLastSyncInfo] = useState<{
    timeUtc: string;
    sourceDeviceName?: string;
  } | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const pingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const activePaperRef = useRef<{ paperId: string; questionIndex: number; paperHash?: string } | null>(null);
  const manuallyClosedRef = useRef(false);

  // Live focus & mouse state tracked in refs for low-overhead real-time reporting
  const telemetryStateRef = useRef({
    windowFocused: typeof document !== 'undefined' ? document.hasFocus() : true,
    visibilityState: typeof document !== 'undefined' ? document.visibilityState : 'visible',
    pointerInViewport: true,
    mouseX: null as number | null,
    mouseY: null as number | null,
    viewportW: typeof window !== 'undefined' ? window.innerWidth : 1280,
    viewportH: typeof window !== 'undefined' ? window.innerHeight : 720,
    hoveredZone: 'page_blank',
    focusLossCount: 0,
    leaveViewportCount: 0,
    lastSentAt: 0,
    lastReportedSecurityAlert: null as string | null,
  });

  const sendJson = useCallback((payload: Record<string, any>): boolean => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }, []);

  const flushTelemetryNow = useCallback(
    (extraFields?: Record<string, any>) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      const st = telemetryStateRef.current;
      const ctx = telemetryContextRef.current;
      st.lastSentAt = Date.now();
      ws.send(
        JSON.stringify({
          type: 'client_telemetry',
          window_focused: st.windowFocused,
          visibility_state: st.visibilityState,
          pointer_in_viewport: st.pointerInViewport,
          mouse_x: st.mouseX,
          mouse_y: st.mouseY,
          viewport_w: st.viewportW,
          viewport_h: st.viewportH,
          hovered_zone: st.hoveredZone,
          focus_loss_count: st.focusLossCount,
          leave_viewport_count: st.leaveViewportCount,
          page_mode: ctx.pageMode || 'user_center',
          exam_state: ctx.examState || 'idle',
          active_paper_id: ctx.paperId ?? activePaperRef.current?.paperId ?? null,
          paper_difficulty: ctx.paperDifficulty ?? null,
          current_question_index:
            ctx.currentQuestionIndex ?? activePaperRef.current?.questionIndex ?? 0,
          answered_count: ctx.answeredCount ?? 0,
          total_questions: ctx.totalQuestions ?? 0,
          dom_purged: Boolean(ctx.domPurged),
          shield_master_on: Boolean(ctx.shieldMasterOn),
          security_alert_count: ctx.securityAlertCount ?? 0,
          last_security_alert: ctx.lastSecurityAlert ?? null,
          ...extraFields,
        })
      );
      return true;
    },
    []
  );

  useEffect(() => {
    if (!token) {
      manuallyClosedRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {}
        wsRef.current = null;
      }
      setStatus('disconnected');
      setDevices([]);
      return;
    }

    manuallyClosedRef.current = false;
    const identity = getOrCreateDeviceIdentity();
    setDeviceId(identity.deviceId);
    setDeviceName(identity.deviceName);

    let retryAttempt = 0;

    const connect = () => {
      if (manuallyClosedRef.current) return;
      setStatus('connecting');

      const url = resolveWsUrl(identity.deviceId, identity.deviceName);
      let ws: WebSocket;
      try {
        // Pass authentication token in the Sec-WebSocket-Protocol request header
        ws = new WebSocket(url, ['uniexam-v1', `bearer.${token}`]);
      } catch {
        setStatus('disconnected');
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        retryAttempt = 0;
        setStatus('connected');
        if (pingTimerRef.current) clearInterval(pingTimerRef.current);
        pingTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000);

        if (activePaperRef.current) {
          ws.send(
            JSON.stringify({
              type: 'join_paper',
              paper_id: activePaperRef.current.paperId,
              paper_hash: activePaperRef.current.paperHash,
              current_question_index: activePaperRef.current.questionIndex,
            })
          );
        }

        // Send initial telemetry snapshot immediately on connect
        if (typeof document !== 'undefined') {
          telemetryStateRef.current.windowFocused = document.hasFocus();
          telemetryStateRef.current.visibilityState = document.visibilityState;
          telemetryStateRef.current.viewportW = window.innerWidth;
          telemetryStateRef.current.viewportH = window.innerHeight;
        }
        flushTelemetryNow();
      };

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (!msg || typeof msg.type !== 'string') return;

          switch (msg.type) {
            case 'connected':
              if (Array.isArray(msg.devices)) {
                setDevices(msg.devices);
              }
              break;

            case 'presence_update':
              if (Array.isArray(msg.devices)) {
                setDevices(msg.devices);
              }
              break;

            case 'admin_live_state':
              if (Array.isArray(msg.connections)) {
                setAdminLiveConnections(msg.connections);
              }
              if (Array.isArray(msg.events)) {
                setAdminLiveEvents(msg.events);
              }
              break;

            case 'admin_live_event':
              if (Array.isArray(msg.connections)) {
                setAdminLiveConnections(msg.connections);
              }
              if (msg.event && typeof msg.event === 'object') {
                setAdminLiveEvents((prev) => {
                  const filtered = prev.filter((e) => e.id !== msg.event.id);
                  return [msg.event as AdminLiveEvent, ...filtered].slice(0, 150);
                });
              }
              break;

            case 'paper_state':
              callbacksRef.current.onPaperState?.(msg as PaperStateEvent);
              break;

            case 'progress_saved':
              setLastSyncInfo({
                timeUtc: msg.last_update_time_utc || new Date().toISOString(),
                sourceDeviceName: identity.deviceName,
              });
              callbacksRef.current.onProgressSaved?.(msg);
              break;

            case 'progress_synced':
              setLastSyncInfo({
                timeUtc: msg.last_update_time_utc || new Date().toISOString(),
                sourceDeviceName: msg.source_device_name || '其他设备',
              });
              callbacksRef.current.onProgressSynced?.(msg as ProgressSyncedEvent);
              break;

            case 'resolved_sync':
              callbacksRef.current.onResolvedSync?.(msg as ResolvedSyncEvent);
              break;

            case 'cursor_synced':
              callbacksRef.current.onCursorSynced?.(msg as CursorSyncedEvent);
              break;

            case 'exam_finished':
              callbacksRef.current.onExamFinished?.(msg as ExamFinishedEvent);
              break;

            case 'exam_created':
              callbacksRef.current.onExamCreated?.(msg as ExamCreatedEvent);
              break;

            case 'admin_paper_updated':
              callbacksRef.current.onAdminPaperUpdated?.(msg);
              break;

            case 'sync_error':
              callbacksRef.current.onSyncError?.(msg);
              break;

            case 'kicked':
              manuallyClosedRef.current = true;
              callbacksRef.current.onKicked?.({
                reason: msg.reason || '当前设备连接已被断开',
              });
              break;

            default:
              break;
          }
        } catch {
          // Ignore malformed WS frames
        }
      };

      ws.onclose = (evt) => {
        if (pingTimerRef.current) clearInterval(pingTimerRef.current);
        setStatus('disconnected');
        if (evt.code === 4001 || evt.code === 4002 || manuallyClosedRef.current) {
          return;
        }
        const delay = Math.min(1000 * Math.pow(1.6, retryAttempt), 8000);
        retryAttempt += 1;
        reconnectTimerRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        // Handled by onclose
      };
    };

    connect();

    return () => {
      manuallyClosedRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (pingTimerRef.current) clearInterval(pingTimerRef.current);
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {}
        wsRef.current = null;
      }
    };
  }, [token, flushTelemetryNow]);

  // Real-time window focus, visibility, and mouse pointer telemetry listeners
  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') return;

    const st = telemetryStateRef.current;

    const handleWindowFocus = () => {
      st.windowFocused = true;
      st.visibilityState = document.visibilityState;
      flushTelemetryNow();
    };

    const handleWindowBlur = () => {
      if (st.windowFocused) {
        st.focusLossCount += 1;
      }
      st.windowFocused = false;
      st.visibilityState = document.visibilityState;
      flushTelemetryNow();
    };

    const handleVisibilityChange = () => {
      const nextVis = document.visibilityState;
      if (st.visibilityState === 'visible' && nextVis !== 'visible') {
        st.focusLossCount += 1;
        st.windowFocused = false;
      } else if (nextVis === 'visible') {
        st.windowFocused = document.hasFocus();
      }
      st.visibilityState = nextVis;
      flushTelemetryNow();
    };

    const handleMouseLeaveViewport = () => {
      if (st.pointerInViewport) {
        st.leaveViewportCount += 1;
      }
      st.pointerInViewport = false;
      st.hoveredZone = 'outside_viewport';
      flushTelemetryNow();
    };

    const handleMouseEnterViewport = (e: MouseEvent) => {
      st.pointerInViewport = true;
      st.viewportW = window.innerWidth || 1280;
      st.viewportH = window.innerHeight || 720;
      st.mouseX = Math.max(0, Math.min(1, e.clientX / st.viewportW));
      st.mouseY = Math.max(0, Math.min(1, e.clientY / st.viewportH));
      st.hoveredZone = resolveHoveredZoneFromPointerEvent(e);
      flushTelemetryNow();
    };

    const handlePointerMove = (e: PointerEvent) => {
      const w = window.innerWidth || 1280;
      const h = window.innerHeight || 720;
      st.viewportW = w;
      st.viewportH = h;
      st.pointerInViewport = true;
      st.mouseX = Math.max(0, Math.min(1, e.clientX / w));
      st.mouseY = Math.max(0, Math.min(1, e.clientY / h));

      const prevZone = st.hoveredZone;
      const nextZone = resolveHoveredZoneFromPointerEvent(e);
      st.hoveredZone = nextZone;

      const now = Date.now();
      // Immediate send if semantic zone changed, otherwise throttle to 250ms
      if (nextZone !== prevZone || now - st.lastSentAt >= 250) {
        flushTelemetryNow();
      }
    };

    const handleResize = () => {
      st.viewportW = window.innerWidth || 1280;
      st.viewportH = window.innerHeight || 720;
      flushTelemetryNow();
    };

    window.addEventListener('focus', handleWindowFocus);
    window.addEventListener('blur', handleWindowBlur);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    document.documentElement.addEventListener('mouseleave', handleMouseLeaveViewport);
    document.documentElement.addEventListener('mouseenter', handleMouseEnterViewport);
    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    window.addEventListener('resize', handleResize, { passive: true });

    return () => {
      window.removeEventListener('focus', handleWindowFocus);
      window.removeEventListener('blur', handleWindowBlur);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      document.documentElement.removeEventListener('mouseleave', handleMouseLeaveViewport);
      document.documentElement.removeEventListener('mouseenter', handleMouseEnterViewport);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('resize', handleResize);
    };
  }, [flushTelemetryNow]);

  // Push telemetry immediately whenever high-level exam/security context changes
  useEffect(() => {
    if (status !== 'connected') return;
    const st = telemetryStateRef.current;
    const latestAlert = telemetryContext?.lastSecurityAlert ?? null;
    if (latestAlert && latestAlert !== st.lastReportedSecurityAlert) {
      st.lastReportedSecurityAlert = latestAlert;
      flushTelemetryNow({ security_event: latestAlert });
    } else {
      flushTelemetryNow();
    }
  }, [
    status,
    telemetryContext?.pageMode,
    telemetryContext?.examState,
    telemetryContext?.paperId,
    telemetryContext?.currentQuestionIndex,
    telemetryContext?.answeredCount,
    telemetryContext?.totalQuestions,
    telemetryContext?.domPurged,
    telemetryContext?.shieldMasterOn,
    telemetryContext?.securityAlertCount,
    telemetryContext?.lastSecurityAlert,
    flushTelemetryNow,
  ]);

  const joinPaper = useCallback(
    (paperId: string, currentQuestionIndex: number = 0, paperHash?: string) => {
      activePaperRef.current = { paperId, questionIndex: currentQuestionIndex, paperHash };
      return sendJson({
        type: 'join_paper',
        paper_id: paperId,
        paper_hash: paperHash,
        current_question_index: currentQuestionIndex,
      });
    },
    [sendJson]
  );

  const requestResolveSync = useCallback(
    (paperId: string, paperHash?: string) => {
      if (!paperHash) return false;
      return sendJson({
        type: 'resolve_sync',
        paper_id: paperId,
        paper_hash: paperHash,
      });
    },
    [sendJson]
  );

  const leavePaper = useCallback(() => {
    activePaperRef.current = null;
    return sendJson({ type: 'leave_paper' });
  }, [sendJson]);

  const sendCursorMove = useCallback(
    (paperId: string, currentQuestionIndex: number) => {
      activePaperRef.current = {
        paperId,
        questionIndex: currentQuestionIndex,
        paperHash: activePaperRef.current?.paperHash,
      };
      return sendJson({
        type: 'cursor_move',
        paper_id: paperId,
        current_question_index: currentQuestionIndex,
      });
    },
    [sendJson]
  );

  const syncProgress = useCallback(
    (payload: PaperSubmissionPayload) => {
      return sendJson({
        type: 'sync_progress',
        paper_id: payload.paper_id,
        paper: payload.paper,
        paper_hash: payload.paper_hash,
        result: payload.result,
        current_question_index: payload.current_question_index,
      });
    },
    [sendJson]
  );

  const finishExam = useCallback(
    (payload: PaperSubmissionPayload) => {
      return sendJson({
        type: 'finish_exam',
        paper_id: payload.paper_id,
        paper: payload.paper,
        paper_hash: payload.paper_hash,
        result: payload.result,
      });
    },
    [sendJson]
  );

  const kickDevice = useCallback(
    (targetDeviceId: string) => {
      return sendJson({
        type: 'kick_device',
        target_device_id: targetDeviceId,
      });
    },
    [sendJson]
  );

  const requestAdminLiveState = useCallback(() => {
    return sendJson({
      type: 'admin_request_live_state',
    });
  }, [sendJson]);

  const adminKickDevice = useCallback(
    (targetUid: string, targetDeviceId: string, reason?: string) => {
      return sendJson({
        type: 'admin_kick_device',
        target_uid: targetUid,
        target_device_id: targetDeviceId,
        reason,
      });
    },
    [sendJson]
  );

  const clearAdminLiveEvents = useCallback(() => {
    setAdminLiveEvents([]);
  }, []);

  return {
    status,
    deviceId,
    deviceName,
    devices,
    adminLiveConnections,
    adminLiveEvents,
    lastSyncInfo,
    joinPaper,
    requestResolveSync,
    leavePaper,
    sendCursorMove,
    syncProgress,
    finishExam,
    kickDevice,
    requestAdminLiveState,
    adminKickDevice,
    clearAdminLiveEvents,
  };
}
