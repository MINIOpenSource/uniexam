"use client";

import React, { useMemo, useState } from 'react';
import type { ConnectedDevice, AdminLiveEvent } from '@/types/exam';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
  Activity,
  AlertTriangle,
  Crosshair,
  Eye,
  EyeOff,
  FileText,
  Monitor,
  MousePointer,
  Radio,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserX,
  Wifi,
} from 'lucide-react';

interface AdminLiveMonitorViewProps {
  wsStatus: string;
  currentDeviceId: string;
  connections: ConnectedDevice[];
  events: AdminLiveEvent[];
  onRequestRefresh: () => void;
  onKickDevice: (uid: string, deviceId: string, reason?: string) => void;
  onClearEvents: () => void;
  onInspectPaper?: (paperId: string) => void;
  compactMode?: boolean;
}

const ZONE_LABELS: Record<string, string> = {
  question_stem: '题干阅读区',
  option_A: '选项 A (第 1 项)',
  option_B: '选项 B (第 2 项)',
  option_C: '选项 C (第 3 项)',
  option_D: '选项 D (第 4 项)',
  question_options: '选项列表区',
  question_nav: '题号导航栏',
  exam_actions: '翻页/交卷栏',
  header: '顶部状态栏',
  page_blank: '页面空白区',
  outside_viewport: '浏览器视口外',
};

const PAGE_MODE_LABELS: Record<string, string> = {
  exam_active_direct: '正在作答试卷',
  user_center: '考生个人中心',
  admin_panel: '管理后台面板',
};

function formatTimeShort(iso?: string | null): string {
  if (!iso) return '-';
  try {
    const d = new Date(iso);
    return d.toTimeString().slice(0, 8);
  } catch {
    return '-';
  }
}

export function AdminLiveMonitorView({
  wsStatus,
  currentDeviceId,
  connections,
  events,
  onRequestRefresh,
  onKickDevice,
  onClearEvents,
  onInspectPaper,
  compactMode = false,
}: AdminLiveMonitorViewProps) {
  const [clientFilter, setClientFilter] = useState<'all' | 'exam' | 'anomaly'>('all');
  const [eventFilter, setEventFilter] = useState<'all' | 'focus_pointer' | 'security' | 'exam'>('all');
  const [searchTerm, setSearchTerm] = useState('');

  const stats = useMemo(() => {
    const uniqueUsers = new Set(connections.map((c) => c.uid || c.device_id)).size;
    const activeExamClients = connections.filter(
      (c) => c.page_mode === 'exam_active_direct' || Boolean(c.active_paper_id)
    ).length;
    const unfocusedOrOutside = connections.filter(
      (c) =>
        c.window_focused === false ||
        c.visibility_state === 'hidden' ||
        c.pointer_in_viewport === false
    ).length;
    const securityAlerted = connections.filter(
      (c) => Boolean(c.dom_purged) || (c.security_alert_count || 0) > 0
    ).length;
    const totalBlurs = connections.reduce((acc, c) => acc + (c.focus_loss_count || 0), 0);
    const totalPointerLeaves = connections.reduce(
      (acc, c) => acc + (c.leave_viewport_count || 0),
      0
    );

    return {
      totalConnections: connections.length,
      uniqueUsers,
      activeExamClients,
      unfocusedOrOutside,
      securityAlerted,
      totalBlurs,
      totalPointerLeaves,
    };
  }, [connections]);

  const filteredConnections = useMemo(() => {
    return connections.filter((conn) => {
      if (clientFilter === 'exam') {
        if (conn.page_mode !== 'exam_active_direct' && !conn.active_paper_id) return false;
      } else if (clientFilter === 'anomaly') {
        const hasIssue =
          conn.window_focused === false ||
          conn.visibility_state === 'hidden' ||
          conn.pointer_in_viewport === false ||
          Boolean(conn.dom_purged) ||
          (conn.security_alert_count || 0) > 0 ||
          (conn.focus_loss_count || 0) > 0;
        if (!hasIssue) return false;
      }

      if (searchTerm.trim()) {
        const q = searchTerm.toLowerCase();
        const matchUid = (conn.uid || '').toLowerCase().includes(q);
        const matchDev = (conn.device_name || '').toLowerCase().includes(q);
        const matchIp = (conn.ip_address || '').toLowerCase().includes(q);
        const matchPaper = (conn.active_paper_id || '').toLowerCase().includes(q);
        if (!matchUid && !matchDev && !matchIp && !matchPaper) return false;
      }
      return true;
    });
  }, [connections, clientFilter, searchTerm]);

  const filteredEvents = useMemo(() => {
    return events.filter((ev) => {
      if (eventFilter === 'focus_pointer') {
        return ev.category === 'focus' || ev.category === 'pointer';
      }
      if (eventFilter === 'security') {
        return ev.category === 'security';
      }
      if (eventFilter === 'exam') {
        return ev.category === 'exam';
      }
      return true;
    });
  }, [events, eventFilter]);

  return (
    <div className="space-y-4">
      {/* Live Status Bar & KPI Summary */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 rounded border bg-card px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-2.5 w-2.5">
            {wsStatus === 'connected' && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            )}
            <span
              className={cn(
                'relative inline-flex rounded-full h-2.5 w-2.5',
                wsStatus === 'connected'
                  ? 'bg-emerald-500'
                  : wsStatus === 'connecting'
                  ? 'bg-amber-500'
                  : 'bg-rose-500'
              )}
            />
          </span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-foreground">
                Live 前端状态与鼠标焦点实时监控中心
              </span>
              <Badge variant="outline" className="text-[10px] font-mono h-5">
                {wsStatus === 'connected' ? 'WS 实时流已连接' : 'WS 重连中'}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              实时回传前端窗口焦点 (Focus/Blur)、标签页可见性、鼠标视口坐标与悬停区域、答题进度及反作弊探针状态
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onRequestRefresh}
            className="h-8 text-xs gap-1.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            同步实时快照
          </Button>
        </div>
      </div>

      {/* 4 KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="rounded border bg-card p-3.5 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>在线前端实例</span>
            <Wifi className="h-3.5 w-3.5 text-emerald-500" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-foreground">
              {stats.totalConnections}
            </span>
            <span className="text-xs text-muted-foreground">
              ({stats.uniqueUsers} 名在线用户)
            </span>
          </div>
        </div>

        <div className="rounded border bg-card p-3.5 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>正在作答客户端</span>
            <Activity className="h-3.5 w-3.5 text-primary" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono text-foreground">
              {stats.activeExamClients}
            </span>
            <span className="text-xs text-muted-foreground">活跃考场会话</span>
          </div>
        </div>

        <div className="rounded border bg-card p-3.5 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>当前失焦 / 鼠标离界</span>
            <MousePointer className="h-3.5 w-3.5 text-amber-500" />
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                'text-2xl font-bold font-mono',
                stats.unfocusedOrOutside > 0
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-foreground'
              )}
            >
              {stats.unfocusedOrOutside}
            </span>
            <span className="text-xs text-muted-foreground">
              累计失焦 {stats.totalBlurs} 次 · 离界 {stats.totalPointerLeaves} 次
            </span>
          </div>
        </div>

        <div className="rounded border bg-card p-3.5 space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>安全探针 / F12 告警</span>
            <ShieldAlert className="h-3.5 w-3.5 text-rose-500" />
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                'text-2xl font-bold font-mono',
                stats.securityAlerted > 0
                  ? 'text-rose-600 dark:text-rose-400'
                  : 'text-foreground'
              )}
            >
              {stats.securityAlerted}
            </span>
            <span className="text-xs text-muted-foreground">
              CSSOM 接管 / 异常拦截
            </span>
          </div>
        </div>
      </div>

      {/* Main Split Layout: Left = Live Frontend Matrix, Right = Real-Time Telemetry Event Stream */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* Left 2 Columns: Live Frontend Clients */}
        <div className="xl:col-span-2 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 rounded border bg-card p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                variant={clientFilter === 'all' ? 'default' : 'outline'}
                size="sm"
                className="h-7 text-xs px-2.5"
                onClick={() => setClientFilter('all')}
              >
                全部客户端 ({connections.length})
              </Button>
              <Button
                variant={clientFilter === 'exam' ? 'default' : 'outline'}
                size="sm"
                className="h-7 text-xs px-2.5"
                onClick={() => setClientFilter('exam')}
              >
                正在答题 ({stats.activeExamClients})
              </Button>
              <Button
                variant={clientFilter === 'anomaly' ? 'default' : 'outline'}
                size="sm"
                className="h-7 text-xs px-2.5"
                onClick={() => setClientFilter('anomaly')}
              >
                失焦 / 异常 ({stats.unfocusedOrOutside + stats.securityAlerted})
              </Button>
            </div>

            <div className="relative w-full sm:w-56">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                type="search"
                placeholder="搜索用户名 / 设备 / IP / 试卷..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-8 h-7 text-xs"
              />
            </div>
          </div>

          {filteredConnections.length === 0 ? (
            <div className="rounded border bg-card py-12 text-center text-xs text-muted-foreground">
              当前筛选条件下暂无在线前端连接
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {filteredConnections.slice(0, compactMode ? 6 : undefined).map((conn) => {
                const isSelf = conn.device_id === currentDeviceId;
                const isFocused = conn.window_focused !== false;
                const isVisible = conn.visibility_state !== 'hidden';
                const inViewport = conn.pointer_in_viewport !== false;
                const isAlert =
                  Boolean(conn.dom_purged) || (conn.security_alert_count || 0) > 0;
                const isExamActive =
                  conn.page_mode === 'exam_active_direct' || Boolean(conn.active_paper_id);

                const mx =
                  typeof conn.mouse_x === 'number'
                    ? Math.max(0, Math.min(1, conn.mouse_x))
                    : 0.5;
                const my =
                  typeof conn.mouse_y === 'number'
                    ? Math.max(0, Math.min(1, conn.mouse_y))
                    : 0.5;
                const hasMouseCoords =
                  typeof conn.mouse_x === 'number' && typeof conn.mouse_y === 'number';
                const zoneKey = conn.hovered_zone || 'page_blank';
                const zoneLabel = ZONE_LABELS[zoneKey] || zoneKey;

                return (
                  <div
                    key={`${conn.uid}-${conn.device_id}`}
                    className={cn(
                      'rounded border bg-card flex flex-col justify-between transition-colors',
                      isAlert
                        ? 'border-rose-500/70 bg-rose-500/[0.03]'
                        : !isFocused || !isVisible
                        ? 'border-amber-500/70 bg-amber-500/[0.03]'
                        : !inViewport
                        ? 'border-amber-500/40'
                        : 'border-border'
                    )}
                  >
                    <div>
                      {/* Card Header */}
                      <div className="px-3.5 py-2.5 border-b bg-muted/20 flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-mono font-bold text-sm text-foreground">
                              {conn.uid || '未知用户'}
                            </span>
                            {isSelf && (
                              <Badge variant="secondary" className="text-[10px] h-4 px-1">
                                当前管理员终端
                              </Badge>
                            )}
                            <Badge variant="outline" className="text-[10px] h-4 px-1 font-normal">
                              {PAGE_MODE_LABELS[conn.page_mode || ''] || conn.page_mode || '在线'}
                            </Badge>
                          </div>
                          <div className="text-[11px] text-muted-foreground font-mono truncate mt-0.5">
                            {conn.device_name} · {conn.ip_address}
                          </div>
                        </div>

                        {/* Focus / Security Status Pill */}
                        <div className="shrink-0">
                          {isAlert ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/50 bg-rose-500/15 px-2 py-0.5 text-[10px] font-medium text-rose-600 dark:text-rose-400">
                              <ShieldAlert className="h-3 w-3" />
                              调试/安全告警
                            </span>
                          ) : !isVisible ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/40 bg-rose-500/10 px-2 py-0.5 text-[10px] font-medium text-rose-600 dark:text-rose-400">
                              <EyeOff className="h-3 w-3" />
                              切屏后台隐藏
                            </span>
                          ) : !isFocused ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/50 bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                              <AlertTriangle className="h-3 w-3" />
                              窗口已失焦
                            </span>
                          ) : !inViewport ? (
                            <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                              <MousePointer className="h-3 w-3" />
                              鼠标移出窗口
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                              <Eye className="h-3 w-3" />
                              焦点正常
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Body: Mini Viewport Radar + Telemetry Details */}
                      <div className="p-3.5 space-y-3">
                        <div className="grid grid-cols-12 gap-3 items-center">
                          {/* Mini 16:10 Live Viewport Radar */}
                          <div className="col-span-5">
                            <div className="relative aspect-[16/11] w-full rounded border border-border/80 bg-muted/40 overflow-hidden select-none">
                              {/* Simulated page layout wireframe */}
                              <div
                                className={cn(
                                  'h-[14%] w-full border-b border-border/50 px-1 flex items-center justify-between',
                                  zoneKey === 'header' && 'bg-primary/20'
                                )}
                              >
                                <span className="text-[7px] font-mono text-muted-foreground">
                                  {conn.viewport_w && conn.viewport_h
                                    ? `${conn.viewport_w}×${conn.viewport_h}`
                                    : 'VIEWPORT'}
                                </span>
                                <span className="h-1 w-1 rounded-full bg-emerald-500" />
                              </div>

                              <div className="p-1.5 space-y-1 h-[86%] flex flex-col justify-between">
                                {/* Question Nav Bar */}
                                <div
                                  className={cn(
                                    'h-[14%] rounded-[2px] border border-border/50 bg-background/60',
                                    zoneKey === 'question_nav' &&
                                      'border-primary bg-primary/20'
                                  )}
                                />
                                {/* Question Stem */}
                                <div
                                  className={cn(
                                    'h-[22%] rounded-[2px] border border-border/60 bg-background/80 px-1 flex items-center',
                                    zoneKey === 'question_stem' &&
                                      'border-primary bg-primary/20'
                                  )}
                                >
                                  <span className="text-[7px] font-mono text-muted-foreground truncate">
                                    {isExamActive
                                      ? `Q${(conn.current_question_index || 0) + 1} 题干`
                                      : '主内容区'}
                                  </span>
                                </div>
                                {/* 4 Option Slots */}
                                <div className="space-y-0.5 flex-1 flex flex-col justify-center">
                                  {(['option_A', 'option_B', 'option_C', 'option_D'] as const).map(
                                    (optKey, idx) => (
                                      <div
                                        key={optKey}
                                        className={cn(
                                          'h-[18%] rounded-[1px] border border-border/40 bg-background/50 px-1 flex items-center',
                                          zoneKey === optKey &&
                                            'border-primary bg-primary/25'
                                        )}
                                      >
                                        <span className="text-[6px] font-mono text-muted-foreground">
                                          {String.fromCharCode(65 + idx)}
                                        </span>
                                      </div>
                                    )
                                  )}
                                </div>
                                {/* Bottom Action Bar */}
                                <div
                                  className={cn(
                                    'h-[12%] rounded-[2px] border border-border/50 bg-background/60',
                                    zoneKey === 'exam_actions' &&
                                      'border-primary bg-primary/20'
                                  )}
                                />
                              </div>

                              {/* Live Mouse Pointer Dot */}
                              {hasMouseCoords && inViewport && (
                                <div
                                  className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-1/2 transition-all duration-150 ease-out"
                                  style={{
                                    left: `${(mx * 100).toFixed(1)}%`,
                                    top: `${(my * 100).toFixed(1)}%`,
                                  }}
                                >
                                  <span className="relative flex h-3 w-3 items-center justify-center">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-60" />
                                    <span className="relative inline-flex rounded-full h-2 w-2 bg-primary ring-2 ring-background" />
                                  </span>
                                </div>
                              )}

                              {/* Overlay when unfocused or pointer outside */}
                              {(!isFocused || !isVisible || !inViewport) && (
                                <div className="absolute inset-0 bg-background/75 backdrop-blur-[1px] flex flex-col items-center justify-center text-center p-1">
                                  <span className="text-[9px] font-semibold text-amber-600 dark:text-amber-400">
                                    {!isVisible
                                      ? '标签页已隐藏'
                                      : !isFocused
                                      ? '窗口已失焦'
                                      : '鼠标移出视口'}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Right 7 Columns: Live Focus & Pointer Readout */}
                          <div className="col-span-7 space-y-1.5 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">悬停区域:</span>
                              <span className="font-medium text-foreground truncate max-w-[130px]">
                                {zoneLabel}
                              </span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">鼠标坐标:</span>
                              <span className="font-mono text-[11px] text-foreground">
                                {hasMouseCoords
                                  ? `X:${Math.round(mx * 100)}% Y:${Math.round(my * 100)}%`
                                  : '未移动'}
                              </span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">窗口/可见性:</span>
                              <span
                                className={cn(
                                  'font-mono text-[11px]',
                                  isFocused && isVisible
                                    ? 'text-emerald-600 dark:text-emerald-400'
                                    : 'text-amber-600 dark:text-amber-400 font-semibold'
                                )}
                              >
                                {isFocused ? '聚焦中' : '已失焦'} /{' '}
                                {isVisible ? '前台可见' : '后台隐藏'}
                              </span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">失焦 / 离界:</span>
                              <span className="font-mono text-[11px] text-foreground">
                                {conn.focus_loss_count || 0} 次 /{' '}
                                {conn.leave_viewport_count || 0} 次
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Active Exam Progress Box */}
                        {conn.active_paper_id && (
                          <div className="rounded border bg-muted/30 px-2.5 py-2 space-y-1.5 text-xs">
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-1.5 min-w-0">
                                <FileText className="h-3.5 w-3.5 text-primary shrink-0" />
                                <span className="font-mono font-medium truncate">
                                  试卷 {conn.active_paper_id.slice(0, 8)}...
                                </span>
                                {conn.paper_difficulty && (
                                  <Badge
                                    variant="secondary"
                                    className="text-[10px] h-4 px-1 font-normal"
                                  >
                                    {conn.paper_difficulty}
                                  </Badge>
                                )}
                              </div>
                              <span className="font-mono text-[11px] text-foreground shrink-0">
                                第 {(conn.current_question_index || 0) + 1}
                                {conn.total_questions ? ` / ${conn.total_questions}` : ''} 题
                              </span>
                            </div>

                            {(conn.total_questions || 0) > 0 && (
                              <div className="space-y-1">
                                <div className="flex justify-between text-[10px] text-muted-foreground">
                                  <span>
                                    已答进度: {conn.answered_count || 0} / {conn.total_questions}
                                  </span>
                                  <span>
                                    {Math.round(
                                      ((conn.answered_count || 0) /
                                        Math.max(1, conn.total_questions || 1)) *
                                        100
                                    )}
                                    %
                                  </span>
                                </div>
                                <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                                  <div
                                    className="h-full bg-primary transition-all duration-300"
                                    style={{
                                      width: `${Math.min(
                                        100,
                                        Math.round(
                                          ((conn.answered_count || 0) /
                                            Math.max(1, conn.total_questions || 1)) *
                                            100
                                        )
                                      )}%`,
                                    }}
                                  />
                                </div>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Security / DOM Purge Alert Box */}
                        {(conn.dom_purged || conn.last_security_alert) && (
                          <div className="rounded border border-rose-500/40 bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-600 dark:text-rose-400 space-y-0.5">
                            <div className="font-semibold flex items-center justify-between">
                              <span>
                                {conn.dom_purged
                                  ? '⚡ 已触发静默 DOM 清空 (CSSOM 伪元素保护中)'
                                  : '⚠️ 安全防护告警'}
                              </span>
                              <span className="font-mono">
                                累计 {conn.security_alert_count || 1} 次
                              </span>
                            </div>
                            {conn.last_security_alert && (
                              <div className="text-[10px] opacity-90 break-words">
                                {conn.last_security_alert}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Card Footer Actions */}
                    <div className="px-3.5 py-2 border-t bg-muted/10 flex items-center justify-between gap-2 text-[11px]">
                      <span className="text-muted-foreground font-mono">
                        心跳: {formatTimeShort(conn.last_active_at)}
                      </span>
                      <div className="flex items-center gap-1.5">
                        {conn.active_paper_id && onInspectPaper && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-6 px-2 text-[11px]"
                            onClick={() => onInspectPaper(conn.active_paper_id!)}
                          >
                            查看试卷
                          </Button>
                        )}
                        {!isSelf && conn.uid && (
                          <Button
                            variant="destructive"
                            size="sm"
                            className="h-6 px-2 text-[11px] gap-1"
                            onClick={() =>
                              onKickDevice(
                                conn.uid!,
                                conn.device_id,
                                '管理员在实时监控台断开了该前端会话'
                              )
                            }
                          >
                            <UserX className="h-3 w-3" />
                            踢下线
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right 1 Column: Real-Time Telemetry & Security Event Stream */}
        <div className="rounded border bg-card flex flex-col h-[560px]">
          <div className="p-3 border-b space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Radio className="h-3.5 w-3.5 text-primary" />
                <span className="text-xs font-semibold text-foreground">
                  实时遥测与焦点事件流 ({filteredEvents.length})
                </span>
              </div>
              {events.length > 0 && (
                <button
                  type="button"
                  onClick={onClearEvents}
                  className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                >
                  <Trash2 className="h-3 w-3" />
                  清空
                </button>
              )}
            </div>

            <div className="flex flex-wrap gap-1">
              {(
                [
                  { id: 'all', label: '全部' },
                  { id: 'focus_pointer', label: '焦点/鼠标' },
                  { id: 'security', label: '安全告警' },
                  { id: 'exam', label: '考试动态' },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setEventFilter(tab.id)}
                  className={cn(
                    'rounded px-2 py-0.5 text-[10px] font-medium transition-colors border',
                    eventFilter === tab.id
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-muted/40 text-muted-foreground hover:bg-muted'
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-2.5 space-y-1.5 font-mono text-[11px]">
            {filteredEvents.length === 0 ? (
              <div className="flex items-center justify-center h-full text-xs text-muted-foreground font-sans">
                暂无实时遥测事件
              </div>
            ) : (
              filteredEvents.map((ev) => {
                const isDanger = ev.severity === 'danger';
                const isWarning = ev.severity === 'warning';
                const isSuccess = ev.severity === 'success';

                return (
                  <div
                    key={ev.id}
                    className={cn(
                      'rounded border px-2.5 py-1.5 space-y-0.5 leading-snug',
                      isDanger
                        ? 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300'
                        : isWarning
                        ? 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300'
                        : isSuccess
                        ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                        : 'border-border bg-muted/20 text-foreground'
                    )}
                  >
                    <div className="flex items-center justify-between gap-2 text-[10px] opacity-80">
                      <span className="font-bold truncate">
                        {ev.uid} · {ev.device_name}
                      </span>
                      <span className="shrink-0">{formatTimeShort(ev.timestamp)}</span>
                    </div>
                    <div className="font-sans text-xs break-words">{ev.message}</div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
