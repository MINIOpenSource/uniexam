"use client";

import type { AdminPaper } from '@/types/admin';
import type { ConnectedDevice } from '@/types/exam';
import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/hooks/useTranslation';
import { useLanguage } from '@/context/LanguageContext';
import { format, formatDistanceToNow, parseISO, type Locale } from 'date-fns';
import { enUS, zhCN, ja, ko, fr, de, es, arSA } from 'date-fns/locale';
import { RefreshCwIcon, UserIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CopyButton } from '@/components/ui/copy-button';

interface AdminPaperCardProps {
  paper: AdminPaper;
  liveDevice?: ConnectedDevice | null;
  onViewDetails: (paper: AdminPaper) => void;
  onDelete: (paperId: string) => void;
  isDeleting: boolean;
  isViewingDetails: boolean;
  selectedPaperIdForAction: string | null;
}

type TimeDisplayMode = 'relative' | 'absolute';

interface ClientTimeDisplayProps {
  dateString: string | null | undefined;
  displayMode: TimeDisplayMode;
  onNaturalLanguageAbsoluteTime: (naturalLanguageAbsoluteTime: string) => void;
  onAbsoluteShortFormatted: (formattedDate: string) => void;
  onRelativeFormatted: (relativeDate: string) => void;
}

const ClientTimeDisplay: React.FC<ClientTimeDisplayProps> = ({
  dateString,
  displayMode,
  onNaturalLanguageAbsoluteTime,
  onAbsoluteShortFormatted,
  onRelativeFormatted,
}) => {
  const { language } = useLanguage();
  const [relativeTime, setRelativeTime] = useState<string>('-');
  const [absoluteShortTime, setAbsoluteShortTime] = useState<string>('-');

  const localeMap: Record<string, Locale> = {
    en: enUS, zh: zhCN, ja: ja, ko: ko, fr: fr, de: de, es: es, ar: arSA,
  };

  useEffect(() => {
    if (!dateString) {
      setRelativeTime('-');
      setAbsoluteShortTime('-');
      onNaturalLanguageAbsoluteTime('-');
      onAbsoluteShortFormatted('-');
      onRelativeFormatted('-');
      return;
    }

    let relDisplay = '-';
    let absShortDisplay = '-';
    let naturalAbsForCopy = dateString;

    try {
      const date = parseISO(dateString);
      const currentDnsLocale = localeMap[language] || enUS;

      relDisplay = formatDistanceToNow(date, { addSuffix: true, locale: currentDnsLocale });
      absShortDisplay = format(date, 'yyyy-MM-dd HH:mm:ss', { locale: currentDnsLocale });
      naturalAbsForCopy = format(date, 'yyyy-MM-dd HH:mm:ss', { locale: currentDnsLocale });
    } catch (e) {
      console.error("Error formatting time:", e);
    }
    setRelativeTime(relDisplay);
    setAbsoluteShortTime(absShortDisplay);
    onNaturalLanguageAbsoluteTime(naturalAbsForCopy);
    onAbsoluteShortFormatted(absShortDisplay);
    onRelativeFormatted(relDisplay);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateString, language]);

  const timeToDisplay = displayMode === 'relative' ? relativeTime : absoluteShortTime;

  return (
    <span className="text-xs font-mono">{timeToDisplay}</span>
  );
};

export function AdminPaperCard({
  paper,
  liveDevice,
  onViewDetails,
  onDelete,
  isDeleting,
  isViewingDetails,
  selectedPaperIdForAction
}: AdminPaperCardProps) {
  const { t } = useTranslation();
  const [isCreationIpVisible, setIsCreationIpVisible] = useState(false);
  const [isSubmissionIpVisible, setIsSubmissionIpVisible] = useState(false);
  const [isLastUpdateIpVisible, setIsLastUpdateIpVisible] = useState(false);

  const [creationTimeForCopy, setCreationTimeForCopy] = useState(paper.creation_time_utc || '-');
  const [submissionTimeForCopy, setSubmissionTimeForCopy] = useState(paper.submission_time_utc || '-');
  const [lastUpdateTimeForCopy, setLastUpdateTimeForCopy] = useState(paper.last_update_time_utc || '-');
  
  const [creationTimeDisplayMode, setCreationTimeDisplayMode] = useState<TimeDisplayMode>('absolute');
  const [submissionTimeDisplayMode, setSubmissionTimeDisplayMode] = useState<TimeDisplayMode>('absolute');
  const [lastUpdateTimeDisplayMode, setLastUpdateTimeDisplayMode] = useState<TimeDisplayMode>('absolute');

  const [, setCreationTimeAbsoluteShort] = useState<string>('-');
  const [, setCreationTimeRelative] = useState<string>('-');
  const [, setSubmissionTimeAbsoluteShort] = useState<string>('-');
  const [, setSubmissionTimeRelative] = useState<string>('-');
  const [, setLastUpdateTimeAbsoluteShort] = useState<string>('-');
  const [, setLastUpdateTimeRelative] = useState<string>('-');

  const getStatusBadge = () => {
    if (paper.pass_status === null) {
      return <Badge variant="outline" className="text-xs rounded font-normal">{t('admin.papers.table.statusUnfinished')}</Badge>;
    }
    switch (paper.pass_status?.toUpperCase()) {
      case 'PASSED':
        return (
          <Badge variant="outline" className="text-xs rounded font-normal border-emerald-600 text-emerald-700 dark:text-emerald-400">
            {t('userCenter.history.statusPassed')}
          </Badge>
        );
      case 'FAILED':
        return (
          <Badge variant="outline" className="text-xs rounded font-normal border-red-600 text-red-700 dark:text-red-400">
            {t('userCenter.history.statusFailed')}
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="text-xs rounded font-normal">
            {paper.pass_status || t('admin.papers.table.statusUnfinished')}
          </Badge>
        );
    }
  };

  const getDifficultyBadge = () => {
    if (!paper.difficulty) return null;
    if (paper.difficulty === 'easy' || paper.difficulty === 'hybrid' || paper.difficulty === 'hard') {
      return (
        <Badge variant="secondary" className="text-xs rounded font-normal">
          {t(`difficulty.${paper.difficulty}.label` as any)}
        </Badge>
      );
    }
    return <Badge variant="outline" className="text-xs rounded font-normal">{t('userCenter.history.unknownDifficulty')}</Badge>;
  };

  const truncatedPaperId = paper.paper_id && paper.paper_id.length > 8
    ? `${paper.paper_id.substring(0, 8)}...`
    : (paper.paper_id || '-');

  const renderInfoRow = (
    labelKey: string,
    value: string | number | null | undefined,
    isIpField?: boolean,
    ipVisible?: boolean,
    setIpVisible?: React.Dispatch<React.SetStateAction<boolean>>,
  ) => {
    if (!value && value !== 0 && !isIpField) return null;
    if (isIpField && (!paper[labelKey === 'admin.papers.table.creationIp' ? 'creation_ip' : labelKey === 'admin.papers.table.submissionIp' ? 'submission_ip' : 'last_update_ip' as keyof AdminPaper])) return null;

    return (
      <div className="flex justify-between items-center py-0.5">
        <span className="text-muted-foreground text-xs whitespace-nowrap">
          {t(labelKey as any)}:
        </span>
        <div className="flex items-center gap-1">
          {isIpField ? (
            value && ipVisible && setIpVisible ? (
              <>
                <span className="font-mono text-xs break-all">{value}</span>
                {value && <CopyButton textToCopy={String(value)} toastMessageKey="copyButton.toast.success.ipCopied" size="sm" className="p-0.5 h-5 w-5" iconClassName="h-3 w-3" />}
              </>
            ) : value && setIpVisible ? (
              <Button variant="link" size="sm" className="p-0 h-auto text-xs hover:underline text-muted-foreground" onClick={() => setIpVisible(true)}>
                {t('admin.papers.card.revealIp')}
              </Button>
            ) : (
              !value && <span className="font-mono text-xs">-</span>
            )
          ) : (value || value === 0) && typeof value === 'number' && labelKey === 'admin.papers.table.score' ? (
            <>
              <span className="font-mono text-xs">{value}</span>
              <CopyButton textToCopy={String(value)} toastMessageKey="copyButton.toast.success.genericFieldValueCopied" size="sm" className="p-0.5 h-5 w-5" iconClassName="h-3 w-3" />
            </>
          ) : value || value === 0 ? (
            <span className="text-xs">{value}</span>
          ) : (
            <span className="font-mono text-xs">-</span>
          )}
        </div>
      </div>
    );
  };

  const renderTimeField = (
    labelKey: string,
    dateString: string | null | undefined,
    displayMode: TimeDisplayMode,
    setDisplayMode: React.Dispatch<React.SetStateAction<TimeDisplayMode>>,
    copyTextSetter: React.Dispatch<React.SetStateAction<string>>,
    absoluteShortSetter: React.Dispatch<React.SetStateAction<string>>,
    relativeSetter: React.Dispatch<React.SetStateAction<string>>,
    copyValue: string
  ) => {
    if (!dateString) return null;

    return (
      <div className="flex justify-between items-center py-0.5">
        <span className="text-muted-foreground text-xs whitespace-nowrap">
          {t(labelKey as any)}:
        </span>
        <div className="flex items-center gap-1">
          <ClientTimeDisplay
            dateString={dateString}
            displayMode={displayMode}
            onNaturalLanguageAbsoluteTime={copyTextSetter}
            onAbsoluteShortFormatted={absoluteShortSetter}
            onRelativeFormatted={relativeSetter}
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5 p-0 text-muted-foreground hover:text-foreground"
            onClick={() => setDisplayMode(prev => prev === 'relative' ? 'absolute' : 'relative')}
            title={displayMode === 'relative' ? t('admin.papers.card.timeToggle.showAbsolute') : t('admin.papers.card.timeToggle.showRelative')}
          >
            <RefreshCwIcon className="h-3 w-3" />
          </Button>
          <CopyButton
            textToCopy={copyValue}
            toastMessageKey="copyButton.toast.success.genericFieldValueCopied"
            size="sm" className="p-0.5 h-5 w-5" iconClassName="h-3 w-3"
          />
        </div>
      </div>
    );
  };

  const numTotal = paper.count ?? 0;
  const numFinished = paper.finished_count ?? 0;
  const numCorrect = paper.correct_count ?? 0;
  const numIncorrect = Math.max(0, numFinished - numCorrect);

  return (
    <div className="w-full rounded border bg-card flex flex-col justify-between">
      <div>
        <div className="px-4 py-3 border-b bg-muted/20 flex justify-between items-start gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="font-mono font-semibold text-sm text-foreground break-all" title={paper.paper_id}>
                {truncatedPaperId}
              </span>
              {paper.paper_id && (
                <CopyButton textToCopy={paper.paper_id} toastMessageKey="copyButton.toast.success.paperIdCopied" size="sm" className="p-0.5 h-5 w-5 shrink-0" iconClassName="h-3 w-3" />
              )}
              {paper.user_uid && (
                <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] font-mono text-foreground">
                  <UserIcon className="h-3 w-3 text-muted-foreground" />
                  {paper.user_uid}
                </span>
              )}
            </div>
            {liveDevice && (
              <div className="mt-1 flex items-center gap-1.5 text-[11px] font-mono">
                <span
                  className={cn(
                    "h-2 w-2 rounded-full animate-pulse",
                    liveDevice.window_focused === false || liveDevice.visibility_state === 'hidden'
                      ? "bg-amber-500"
                      : "bg-emerald-500"
                  )}
                />
                <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                  LIVE 正在作答 · 第 {(liveDevice.current_question_index || 0) + 1} 题
                </span>
                <span className="text-muted-foreground">
                  ({liveDevice.window_focused === false ? '窗口失焦' : liveDevice.pointer_in_viewport === false ? '鼠标离界' : '焦点正常'})
                </span>
              </div>
            )}
            {paper.passcode && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5">
                <span className="shrink-0">{t('admin.papers.table.passcode')}:</span>
                <span className="font-mono text-foreground">{paper.passcode}</span>
                <CopyButton textToCopy={paper.passcode} toastMessageKey="copyButton.toast.success.passcodeCopied" size="sm" className="p-0.5 h-5 w-5 shrink-0" iconClassName="h-3 w-3" />
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0">
            {getDifficultyBadge()}
            {getStatusBadge()}
            {paper.score !== null && (
              <Badge variant="outline" className="text-xs rounded font-mono">
                {paper.score}
              </Badge>
            )}
          </div>
        </div>

        <div className="p-4 space-y-1 text-xs">
          {paper.creation_time_utc && renderTimeField('admin.papers.table.creationTime', paper.creation_time_utc, creationTimeDisplayMode, setCreationTimeDisplayMode, setCreationTimeForCopy, setCreationTimeAbsoluteShort, setCreationTimeRelative, creationTimeForCopy)}
          {paper.creation_ip && renderInfoRow('admin.papers.table.creationIp', paper.creation_ip, true, isCreationIpVisible, setIsCreationIpVisible)}

          {paper.submission_time_utc && renderTimeField('admin.papers.table.submissionTime', paper.submission_time_utc, submissionTimeDisplayMode, setSubmissionTimeDisplayMode, setSubmissionTimeForCopy, setSubmissionTimeAbsoluteShort, setSubmissionTimeRelative, submissionTimeForCopy)}
          {paper.submission_ip && renderInfoRow('admin.papers.table.submissionIp', paper.submission_ip, true, isSubmissionIpVisible, setIsSubmissionIpVisible)}

          {paper.last_update_time_utc && renderTimeField('admin.papers.table.lastUpdateTime', paper.last_update_time_utc, lastUpdateTimeDisplayMode, setLastUpdateTimeDisplayMode, setLastUpdateTimeForCopy, setLastUpdateTimeAbsoluteShort, setLastUpdateTimeRelative, lastUpdateTimeForCopy)}
          {paper.last_update_ip && renderInfoRow('admin.papers.table.lastUpdateIp', paper.last_update_ip, true, isLastUpdateIpVisible, setIsLastUpdateIpVisible)}

          {numTotal > 0 && (
            <div className="flex justify-between items-center py-0.5 pt-1 border-t mt-1">
              <span className="text-muted-foreground text-xs">
                {t('exam.progress.completed', { count: numFinished })}
              </span>
              <div className="flex items-center gap-2 font-mono text-xs">
                <span className="text-emerald-600 dark:text-emerald-400">✓ {numCorrect}</span>
                <span className="text-red-600 dark:text-red-400">✗ {numIncorrect}</span>
                <span className="text-muted-foreground">/ {numTotal}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="px-4 py-2.5 border-t bg-muted/10 flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => onViewDetails(paper)}
          disabled={isViewingDetails && selectedPaperIdForAction === paper.paper_id}
        >
          {t('admin.papers.viewAnswersButton')}
        </Button>
        <Button
          variant="destructive"
          size="sm"
          className="h-7 text-xs"
          onClick={() => onDelete(paper.paper_id)}
          disabled={isDeleting && selectedPaperIdForAction === paper.paper_id}
        >
          {t('admin.papers.table.deleteDialog.delete')}
        </Button>
      </div>
    </div>
  );
}
