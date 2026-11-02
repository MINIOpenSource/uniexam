"use client";

import React, { useEffect, useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/hooks/useTranslation';
import type { AdminSectionId } from './AdminSidebar';
import type { ConnectedDevice, AdminLiveEvent } from '@/types/exam';
import type { User } from '@/types/auth';
import type { AdminPaper } from '@/types/admin';
import { fetchAdminPapers, fetchAdminUsers, fetchAdminQuestionBankIndex } from '@/lib/admin-api';
import { AdminLiveMonitorView } from './AdminLiveMonitorView';
import {
  Activity,
  CheckCircle2,
  FileText,
  Library,
  Settings,
  Users,
} from 'lucide-react';

interface AdminHomeViewProps {
  user: User | null;
  onNavigate: (section: AdminSectionId) => void;
  wsStatus: string;
  currentDeviceId: string;
  liveConnections: ConnectedDevice[];
  liveEvents: AdminLiveEvent[];
  onRequestRefreshLive: () => void;
  onKickDevice: (uid: string, deviceId: string, reason?: string) => void;
  onClearEvents: () => void;
  paperUpdateVersion?: number;
}

export function AdminHomeView({
  user,
  onNavigate,
  wsStatus,
  currentDeviceId,
  liveConnections,
  liveEvents,
  onRequestRefreshLive,
  onKickDevice,
  onClearEvents,
  paperUpdateVersion = 0,
}: AdminHomeViewProps) {
  const { t } = useTranslation();

  const [paperStats, setPaperStats] = useState({
    total: 0,
    passed: 0,
    failed: 0,
    unfinished: 0,
    avgScore: 0,
  });
  const [userCount, setUserCount] = useState(0);
  const [questionCount, setQuestionCount] = useState(0);

  const loadSummary = useCallback(async () => {
    if (!user?.token) return;
    try {
      const [papersRes, usersRes, banksRes] = await Promise.allSettled([
        fetchAdminPapers(user.token, 0, 500),
        fetchAdminUsers(user.token, 0, 500),
        fetchAdminQuestionBankIndex(user.token),
      ]);

      if (papersRes.status === 'fulfilled' && Array.isArray(papersRes.value)) {
        const list = papersRes.value as AdminPaper[];
        let passed = 0;
        let failed = 0;
        let unfinished = 0;
        let scoreSum = 0;
        let gradedCount = 0;
        for (const p of list) {
          const st = p.pass_status?.toUpperCase();
          if (st === 'PASSED') passed += 1;
          else if (st === 'FAILED') failed += 1;
          else unfinished += 1;
          if (typeof p.score === 'number') {
            scoreSum += p.score;
            gradedCount += 1;
          }
        }
        setPaperStats({
          total: list.length,
          passed,
          failed,
          unfinished,
          avgScore: gradedCount > 0 ? Math.round(scoreSum / gradedCount) : 0,
        });
      }

      if (usersRes.status === 'fulfilled' && Array.isArray(usersRes.value)) {
        setUserCount(usersRes.value.length);
      }

      if (banksRes.status === 'fulfilled' && Array.isArray(banksRes.value)) {
        const totalQ = banksRes.value.reduce(
          (acc, b) => acc + (b.question_count || 0),
          0
        );
        setQuestionCount(totalQ);
      }
    } catch {}
  }, [user?.token]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary, paperUpdateVersion]);

  const gradedTotal = paperStats.passed + paperStats.failed;
  const passRate =
    gradedTotal > 0 ? Math.round((paperStats.passed / gradedTotal) * 100) : 0;

  return (
    <div className="space-y-6">
      {/* Top Overview Navigation & System Summary Cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col justify-between rounded border bg-card p-4 space-y-3">
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{t('admin.home.papers.title')}</span>
              <FileText className="h-4 w-4 text-primary" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold font-mono text-foreground">
                {paperStats.total}
              </span>
              <span className="text-xs text-muted-foreground">
                通过率 {passRate}% · 均分 {paperStats.avgScore}
              </span>
            </div>
            <div className="text-[11px] text-muted-foreground font-mono">
              通过 {paperStats.passed} · 未过 {paperStats.failed} · 作答中{' '}
              {paperStats.unfinished}
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="w-full h-8 text-xs"
            onClick={() => onNavigate('papers')}
          >
            {t('admin.home.papers.button')}
          </Button>
        </div>

        <div className="flex flex-col justify-between rounded border bg-card p-4 space-y-3">
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{t('admin.home.questionBanks.title')}</span>
              <Library className="h-4 w-4 text-primary" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold font-mono text-foreground">
                {questionCount}
              </span>
              <span className="text-xs text-muted-foreground">道受保护试题</span>
            </div>
            <div className="text-[11px] text-muted-foreground">
              支持简单 / 混合 / 困难三级题库动态管理
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="w-full h-8 text-xs"
            onClick={() => onNavigate('questionBanks')}
          >
            {t('admin.home.questionBanks.button')}
          </Button>
        </div>

        <div className="flex flex-col justify-between rounded border bg-card p-4 space-y-3">
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{t('admin.users.view.title')}</span>
              <Users className="h-4 w-4 text-primary" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold font-mono text-foreground">
                {userCount}
              </span>
              <span className="text-xs text-muted-foreground">
                名注册账号 ({liveConnections.length} 台设备在线)
              </span>
            </div>
            <div className="text-[11px] text-muted-foreground">
              支持角色权限配置、资料编辑与会话吊销
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="w-full h-8 text-xs"
            onClick={() => onNavigate('users')}
          >
            {t('admin.users.view.button')}
          </Button>
        </div>

        <div className="flex flex-col justify-between rounded border bg-card p-4 space-y-3">
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>全屏实时监控中心</span>
              <Activity className="h-4 w-4 text-emerald-500" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
                {liveConnections.length}
              </span>
              <span className="text-xs text-muted-foreground">
                路前端遥测流在线
              </span>
            </div>
            <div className="text-[11px] text-muted-foreground">
              实时追踪鼠标视口焦点、切屏失焦与 F12 告警
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Button
              size="sm"
              variant="default"
              className="w-full h-8 text-xs"
              onClick={() => onNavigate('liveMonitor')}
            >
              独立监控大屏
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="w-full h-8 text-xs"
              onClick={() => onNavigate('settings')}
            >
              {t('admin.nav.settings')}
            </Button>
          </div>
        </div>
      </div>

      {/* Embedded Live Frontend & Focus Monitor */}
      <AdminLiveMonitorView
        wsStatus={wsStatus}
        currentDeviceId={currentDeviceId}
        connections={liveConnections}
        events={liveEvents}
        onRequestRefresh={onRequestRefreshLive}
        onKickDevice={onKickDevice}
        onClearEvents={onClearEvents}
        onInspectPaper={() => onNavigate('papers')}
      />
    </div>
  );
}
