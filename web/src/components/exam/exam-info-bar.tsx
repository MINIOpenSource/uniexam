"use client";

import * as React from 'react';
import { useTranslation } from '@/hooks/useTranslation';
import { CopyButton } from '@/components/ui/copy-button';
import type { Difficulty, AutoSaveStatus, WsConnectionStatus } from '@/types/exam';
import { useIsMobile } from '@/hooks/use-mobile';
import { cn } from '@/lib/utils';
import { ThemeToggle } from '@/components/settings/theme-toggle';
import { LanguageToggle } from '@/components/settings/language-toggle';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';

interface ExamInfoBarProps {
  totalElapsedTime: string;
  paperId: string | null | undefined;
  difficulty: Difficulty | null;
  autoSaveStatus: AutoSaveStatus;
  onGoBackToUserCenter?: () => void;
  wsStatus?: WsConnectionStatus;
  devicesCount?: number;
  onOpenDevicesModal?: () => void;
}

export function ExamInfoBar({
  totalElapsedTime,
  paperId,
  difficulty,
  autoSaveStatus,
  onGoBackToUserCenter,
  wsStatus,
  devicesCount = 0,
  onOpenDevicesModal,
}: ExamInfoBarProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const { user, logout } = useAuth();

  const difficultyLabel = difficulty ? t(`difficulty.${difficulty}.label` as any) : '';

  let displayPaperId = paperId;
  if (isMobile && paperId && paperId.length > 10) {
    displayPaperId = `${paperId.substring(0, 6)}...`;
  }

  const renderAutoSaveStatus = () => {
    switch (autoSaveStatus) {
      case 'saving':
        return <span className="text-xs text-muted-foreground">{t('exam.autoSave.saving')}</span>;
      case 'saved':
        return <span className="text-xs text-green-700 dark:text-green-400">{t('exam.autoSave.saved')}</span>;
      case 'error':
        return <span className="text-xs text-destructive">{t('exam.autoSave.error')}</span>;
      case 'idle':
      default:
        return null;
    }
  };

  return (
    <div className="sticky top-0 w-full z-40 flex h-12 items-center justify-between border-b bg-card px-3 sm:px-4">
      <div className="flex items-center gap-3 text-xs">
        {onGoBackToUserCenter && (
          <Button variant="outline" size="sm" onClick={onGoBackToUserCenter} className="h-7 px-2.5 text-xs">
            {t('exam.backToUserCenter')}
          </Button>
        )}
        {paperId && (
          <div className="flex items-center gap-1 text-muted-foreground">
            <span className="hidden sm:inline">{t('result.paperIdLabel')}</span>
            <span className="font-code-extrabold text-foreground">{displayPaperId}</span>
            <CopyButton
              textToCopy={paperId}
              toastMessageKey="copyButton.toast.success.paperIdCopied"
              size="sm"
              className="p-0.5 h-5 w-5"
              iconClassName="h-3 w-3"
            />
          </div>
        )}
        {difficulty && (
          <span className="rounded border bg-muted px-1.5 py-0.5 text-foreground">
            {difficultyLabel}
          </span>
        )}
        {totalElapsedTime && (
          <span className="font-code-extrabold text-foreground">
            {totalElapsedTime}
          </span>
        )}
        {renderAutoSaveStatus()}
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        {onOpenDevicesModal && (
          <Button
            variant="outline"
            size="sm"
            onClick={onOpenDevicesModal}
            title={t('multiDevice.tooltip')}
            className="h-7 gap-1.5 px-2 text-xs"
          >
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                wsStatus === 'connected'
                  ? "bg-green-600"
                  : wsStatus === 'connecting'
                  ? "bg-amber-500"
                  : "bg-slate-400"
              )}
            />
            <span className="hidden sm:inline">{t('multiDevice.tooltip')}</span>
            {devicesCount > 0 && <span className="font-code-extrabold">({devicesCount})</span>}
          </Button>
        )}
        <ThemeToggle />
        <LanguageToggle />
        {user && (
          <Button variant="ghost" size="sm" onClick={logout} className="h-7 px-2 text-xs">
            {t('auth.nav.logout')}
          </Button>
        )}
      </div>
    </div>
  );
}
