"use client";

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/hooks/useTranslation';
import type { Submission } from '@/types/exam';

interface UnansweredConfirmationCardProps {
  summary: {
    indices: number[];
    paperId: string;
    submission: Submission;
  };
  onConfirmSubmit: () => void;
  onCancel: () => void;
  onJumpToQuestion: (index: number) => void;
}

export function UnansweredConfirmationCard({
  summary,
  onConfirmSubmit,
  onCancel,
  onJumpToQuestion,
}: UnansweredConfirmationCardProps) {
  const { t } = useTranslation();
  const { indices } = summary;

  return (
    <div className="w-full max-w-md rounded border bg-card">
      <div className="border-b px-5 py-3.5">
        <h2 className="text-base font-semibold text-foreground">
          {t('unansweredConfirm.title')}
        </h2>
      </div>

      <div className="space-y-3 p-5 text-sm">
        <p className="text-muted-foreground">
          {t('unansweredConfirm.description', { count: indices.length })}
        </p>
        <div className="flex flex-wrap gap-1.5 rounded border bg-muted/30 p-3 max-h-40 overflow-y-auto">
          {indices.map((qIndex) => (
            <Button
              key={qIndex}
              variant="outline"
              size="sm"
              className="h-7 px-2.5 text-xs font-code-extrabold"
              onClick={() => onJumpToQuestion(qIndex)}
            >
              {t('unansweredConfirm.questionLink', { index: qIndex + 1 })}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex justify-end gap-2 border-t bg-muted/30 px-5 py-3">
        <Button onClick={onCancel} variant="outline" size="sm">
          {t('unansweredConfirm.backButton')}
        </Button>
        <Button onClick={onConfirmSubmit} variant="default" size="sm">
          {t('unansweredConfirm.submitAnywayButton')}
        </Button>
      </div>
    </div>
  );
}
