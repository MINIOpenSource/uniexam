"use client";

import type { ResultPageDisplayData } from "@/types/exam";
import { Button } from "@/components/ui/button";
import { useTranslation } from '@/hooks/useTranslation';
import { CopyButton } from "@/components/ui/copy-button";

type ResultStatus = 'success' | 'failed' | 'rate_limited' | 'error';

interface ResultPageProps {
  status: ResultStatus;
  data: ResultPageDisplayData;
  onRetry?: () => void;
}

function formatDuration(ms?: number, translateFn?: (key: any, params?: any) => string): string | null {
  if (typeof ms !== 'number' || ms < 0) return null;
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const tFunc = translateFn || ((key: string) => key);
  return `${minutes}${tFunc('result.timeUnits.minutes')} ${seconds}${tFunc('result.timeUnits.seconds')}`;
}

export function ResultPage({ status, data, onRetry }: ResultPageProps) {
  const { t } = useTranslation();
  const formattedDuration = formatDuration(data.durationMs, t);

  const getHeaderInfo = () => {
    switch (status) {
      case 'success':
        return {
          title: t('result.success.title'),
          message: t('result.success.description'),
          showRetry: false,
        };
      case 'failed':
        return {
          title: t('result.failed.title'),
          message: t('result.failed.content'),
          showRetry: true,
        };
      case 'rate_limited':
        return {
          title: t('result.rateLimited.title'),
          message: data?.message || t('result.rateLimited.content'),
          showRetry: true,
        };
      case 'error':
      default:
        return {
          title: t('result.error.title'),
          message: data?.message || t('result.error.contentDefault'),
          showRetry: true,
        };
    }
  };

  const { title, message, showRetry } = getHeaderInfo();

  return (
    <div className="flex w-full h-full items-center justify-center p-4">
      <div className="w-full max-w-md rounded border bg-card">
        <div className="border-b px-5 py-3.5">
          <h2 className="text-base font-semibold text-foreground">{title}</h2>
        </div>

        <div className="space-y-3 p-5 text-sm">
          {message && <p className="text-muted-foreground">{message}</p>}

          <div className="divide-y rounded border bg-muted/20 text-xs">
            {typeof data.score === 'number' && (
              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-muted-foreground">{t('userCenter.history.scoreLabel')}</span>
                <span className="font-code-extrabold text-sm font-semibold text-foreground">{data.score}</span>
              </div>
            )}
            {data?.passcode && (
              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-muted-foreground">{t('result.success.codePrefix')}</span>
                <div className="flex items-center gap-1.5">
                  <span className="font-code-extrabold text-sm font-semibold text-green-700 dark:text-green-400">
                    {data.passcode}
                  </span>
                  <CopyButton textToCopy={data.passcode} toastMessageKey="copyButton.toast.success.passcodeCopied" size="sm" className="h-5 w-5 p-0.5" iconClassName="h-3 w-3" />
                </div>
              </div>
            )}
            {data.paperId && (
              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-muted-foreground">{t('result.paperIdLabel')}</span>
                <div className="flex items-center gap-1">
                  <span className="font-code-extrabold text-foreground">{data.paperId}</span>
                  <CopyButton textToCopy={data.paperId} toastMessageKey="copyButton.toast.success.paperIdCopied" size="sm" className="h-5 w-5 p-0.5" iconClassName="h-3 w-3" />
                </div>
              </div>
            )}
            {formattedDuration && (
              <div className="flex items-center justify-between px-3 py-2">
                <span className="text-muted-foreground">{t('result.timeTakenLabel')}</span>
                <span className="font-code-extrabold text-foreground">{formattedDuration}</span>
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t bg-muted/30 px-5 py-3">
          {onRetry && (
            <Button onClick={onRetry} variant={showRetry ? "default" : "outline"} size="sm">
              {showRetry ? t('result.button.retry') : t('userCenter.backToHome')}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
