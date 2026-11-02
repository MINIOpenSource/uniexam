"use client";

import type { HistoryItem } from '@/types/auth';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/hooks/useTranslation';
import { cn } from '@/lib/utils';
import * as React from 'react';
import { CopyButton } from '@/components/ui/copy-button';
import Link from 'next/link';

interface UserCenterExamCardProps {
  exam: HistoryItem;
  onViewDetails: (paperId: string) => void;
}

export function UserCenterExamCard({ exam, onViewDetails }: UserCenterExamCardProps) {
  const { t } = useTranslation();

  const effectivePassStatus = exam.pass_status === null ? "IN_PROGRESS" : exam.pass_status;
  const isContinuable = exam.pass_status === null;

  const getStatusLabel = () => {
    switch (effectivePassStatus?.toUpperCase()) {
      case 'PASSED':
        return { text: t('userCenter.history.statusPassed'), cls: "text-green-700 dark:text-green-400 bg-green-500/10 border-green-500/30" };
      case 'FAILED':
        return { text: t('userCenter.history.statusFailed'), cls: "text-destructive bg-destructive/10 border-destructive/30" };
      case 'IN_PROGRESS':
        return { text: t('userCenter.history.statusInProgress'), cls: "text-amber-700 dark:text-amber-400 bg-amber-500/10 border-amber-500/30" };
      default:
        return { text: String(exam.pass_status || t('userCenter.history.statusUnknown')), cls: "text-muted-foreground bg-muted border-border" };
    }
  };

  const statusInfo = getStatusLabel();
  const difficultyText = exam.difficulty
    ? t(`difficulty.${exam.difficulty.toLowerCase()}.label` as any)
    : t('userCenter.history.unknownDifficulty');

  return (
    <div className="flex flex-col justify-between rounded border bg-card p-3.5 text-xs">
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2 border-b pb-2">
          <div className="flex items-center gap-1 min-w-0">
            <span className="font-code-extrabold text-foreground truncate" title={exam.paper_id}>
              {exam.paper_id}
            </span>
            {exam.paper_id && (
              <CopyButton
                textToCopy={exam.paper_id}
                toastMessageKey="copyButton.toast.success.paperIdCopied"
                size="sm"
                className="p-0.5 h-5 w-5 shrink-0"
                iconClassName="h-3 w-3"
              />
            )}
          </div>
          <span className={cn("rounded border px-1.5 py-0.5 text-[11px] font-medium shrink-0", statusInfo.cls)}>
            {statusInfo.text}
          </span>
        </div>

        <div className="flex items-center justify-between text-muted-foreground">
          <span>
            {t('userCenter.history.difficultyLabel')}: <strong className="font-normal text-foreground">{difficultyText}</strong>
          </span>
          <span>
            {t('userCenter.history.scoreLabel')}:{' '}
            <strong className="font-code-extrabold text-foreground">
              {exam.score !== null && exam.score !== undefined ? exam.score : '-'}
            </strong>
          </span>
        </div>
      </div>

      <div className="mt-3 flex justify-end border-t pt-2.5">
        {isContinuable ? (
          <Link href={`/?id=${exam.paper_id}&i=1`} passHref legacyBehavior>
            <Button asChild variant="default" size="sm" className="h-7 px-3 text-xs">
              <a>{t('userCenter.history.continueExamButton')}</a>
            </Button>
          </Link>
        ) : (
          <Button variant="outline" size="sm" className="h-7 px-3 text-xs" onClick={() => onViewDetails(exam.paper_id)}>
            {t('userCenter.history.viewDetailsButton')}
          </Button>
        )}
      </div>
    </div>
  );
}
