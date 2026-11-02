"use client";

import type { PaperFullDetailModel, PaperQuestionInternalDetail } from '@/types/admin';
import React, { useState, useEffect, useRef } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/hooks/useTranslation';
import { CopyButton } from '@/components/ui/copy-button';

const renderWithCodeHighlighting = (text: string | undefined | null): React.ReactNode => {
  if (!text) return null;
  const parts = text.split(/(\`[^`]+\`)/g);
  return parts.map((part, index) => {
    if (part.startsWith('\`') && part.endsWith('\`')) {
      return <code key={index} className="inline-code">{part.slice(1, -1)}</code>;
    }
    return part;
  });
};

export const PaperTableDetailsDialogComponent: React.FC<{
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  selectedPaperDetails: PaperFullDetailModel | null;
  isLoadingDetails: boolean;
}> = ({
  isOpen,
  onOpenChange,
  selectedPaperDetails,
  isLoadingDetails,
}) => {
  const { t } = useTranslation();
  const [currentQuestionDetailIndex, setCurrentQuestionDetailIndex] = useState(0);
  const questionNavScrollContainerRef = useRef<HTMLDivElement>(null);
  const questionButtonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (isOpen && selectedPaperDetails) {
      setCurrentQuestionDetailIndex(0);
      questionButtonRefs.current = Array(selectedPaperDetails.paper_questions?.length || 0)
        .fill(null)
        .map((_, i) => questionButtonRefs.current[i] || (React.createRef<HTMLButtonElement>() as any));
    }
  }, [isOpen, selectedPaperDetails]);

  useEffect(() => {
    if (isOpen && selectedPaperDetails?.paper_questions?.length) {
      const activeButtonElement = questionButtonRefs.current[currentQuestionDetailIndex];
      if (activeButtonElement && questionNavScrollContainerRef.current) {
        activeButtonElement.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
          inline: 'center',
        });
      }
    }
  }, [currentQuestionDetailIndex, isOpen, selectedPaperDetails]);

  const handleNextQuestionDetail = () => {
    if (selectedPaperDetails?.paper_questions && currentQuestionDetailIndex < selectedPaperDetails.paper_questions.length - 1) {
      setCurrentQuestionDetailIndex(prev => prev + 1);
    }
  };

  const handlePreviousQuestionDetail = () => {
    if (currentQuestionDetailIndex > 0) {
      setCurrentQuestionDetailIndex(prev => prev - 1);
    }
  };

  const totalQuestionsInDialog = selectedPaperDetails?.paper_questions?.length || 0;
  const currentQuestionForDialog: PaperQuestionInternalDetail | undefined = selectedPaperDetails?.paper_questions?.[currentQuestionDetailIndex];
  const submittedAnswerForCurrentQuestion = selectedPaperDetails?.submitted_answers_card?.[currentQuestionDetailIndex];

  const displayPaperId = selectedPaperDetails?.paper_id
    ? selectedPaperDetails.paper_id.length > 16
      ? `${selectedPaperDetails.paper_id.substring(0, 8)}...`
      : selectedPaperDetails.paper_id
    : '...';

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-3xl max-h-[90vh] flex flex-col p-0">
        <DialogHeader className="px-5 py-3.5 border-b">
          <DialogTitle className="flex items-center gap-1.5 text-base">
            <span>{t('admin.papers.detailsDialog.titleOnlyAnswers.preamble')}</span>
            <span className="font-mono">{displayPaperId}</span>
            {selectedPaperDetails?.paper_id && (
              <CopyButton textToCopy={selectedPaperDetails.paper_id} toastMessageKey="copyButton.toast.success.paperIdCopied" size="sm" className="p-0.5 h-5 w-5" iconClassName="h-3 w-3" title={t('copyButton.copy')} />
            )}
          </DialogTitle>
        </DialogHeader>

        {isLoadingDetails ? (
          <div className="flex-grow flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mr-2" />
            <p className="text-sm text-muted-foreground">{t('admin.papers.detailsDialog.loading')}</p>
          </div>
        ) : selectedPaperDetails ? (
          <>
            <ScrollArea className="flex-grow px-5 py-4 min-h-0">
              {currentQuestionForDialog ? (
                <div className="rounded border bg-card p-4 space-y-3">
                  <p className="text-sm font-medium break-words">
                    <span className="font-mono mr-1.5">{currentQuestionDetailIndex + 1}.</span>
                    {renderWithCodeHighlighting(currentQuestionForDialog.body)}
                  </p>
                  <div className="space-y-1.5">
                    <p className="text-xs text-muted-foreground">{t('admin.papers.detailsDialog.questionCard.choices')}</p>
                    <ul className="list-none pl-0 text-xs space-y-1.5">
                      {currentQuestionForDialog.correct_choices_map && Object.entries(currentQuestionForDialog.correct_choices_map).map(([key, text]) => (
                        <li
                          key={key}
                          className={cn(
                            "flex items-center p-2 rounded border break-words",
                            submittedAnswerForCurrentQuestion === key
                              ? "bg-emerald-500/10 border-emerald-500/40"
                              : "bg-muted/20 border-border"
                          )}
                        >
                          <span className="font-mono text-emerald-600 dark:text-emerald-400 mr-2 shrink-0">[✓]</span>
                          <span className="flex-grow">{renderWithCodeHighlighting(text)}</span>
                          {submittedAnswerForCurrentQuestion === key && (
                            <Badge variant="outline" className="ml-2 text-xs px-1.5 py-0 border-emerald-500 text-emerald-700 dark:text-emerald-300">
                              {t('admin.papers.detailsDialog.questionCard.selected')}
                            </Badge>
                          )}
                        </li>
                      ))}
                      {currentQuestionForDialog.incorrect_choices_map && Object.entries(currentQuestionForDialog.incorrect_choices_map).map(([key, text]) => (
                        <li
                          key={key}
                          className={cn(
                            "flex items-center p-2 rounded border break-words",
                            submittedAnswerForCurrentQuestion === key
                              ? "bg-red-500/10 border-red-500/40"
                              : "bg-muted/20 border-border"
                          )}
                        >
                          <span className="font-mono text-red-600 dark:text-red-400 mr-2 shrink-0">[✗]</span>
                          <span className="flex-grow">{renderWithCodeHighlighting(text)}</span>
                          {submittedAnswerForCurrentQuestion === key && (
                            <Badge variant="outline" className="ml-2 text-xs px-1.5 py-0 border-red-500 text-red-700 dark:text-red-300">
                              {t('admin.papers.detailsDialog.questionCard.selected')}
                            </Badge>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                  {(submittedAnswerForCurrentQuestion === null || submittedAnswerForCurrentQuestion === "-1") &&
                    (currentQuestionForDialog.correct_choices_map || currentQuestionForDialog.incorrect_choices_map) && (
                      <p className="text-xs text-muted-foreground pt-1">{t('admin.papers.detailsDialog.questionCard.notAnswered')}</p>
                  )}
                </div>
              ) : totalQuestionsInDialog > 0 ? (
                <p className="text-sm text-muted-foreground py-4">{t('admin.papers.detailsDialog.invalidQuestionIndex')}</p>
              ) : (
                <p className="text-sm text-muted-foreground py-4">{t('admin.papers.detailsDialog.noQuestions')}</p>
              )}
            </ScrollArea>

            {totalQuestionsInDialog > 0 && (
              <div className="question-nav-scrollbar w-full border-t border-b bg-muted/20 overflow-x-auto px-5">
                <div ref={questionNavScrollContainerRef} className="flex gap-1 py-2 whitespace-nowrap">
                  {selectedPaperDetails.paper_questions?.map((q, idx) => {
                    const submittedAnswerId = selectedPaperDetails.submitted_answers_card?.[idx];
                    let isCorrect = false;
                    let isAnswered = false;

                    if (submittedAnswerId && submittedAnswerId !== "-1") {
                      isAnswered = true;
                      if (q.correct_choices_map && Object.prototype.hasOwnProperty.call(q.correct_choices_map, submittedAnswerId)) {
                        isCorrect = true;
                      }
                    }

                    const isCurrent = idx === currentQuestionDetailIndex;
                    return (
                      <button
                        key={`nav-detail-${idx}`}
                        type="button"
                        ref={(el) => { questionButtonRefs.current[idx] = el; }}
                        onClick={() => setCurrentQuestionDetailIndex(idx)}
                        className={cn(
                          "h-7 min-w-[2rem] px-1.5 rounded border text-xs font-mono shrink-0 transition-colors",
                          isCurrent
                            ? "border-primary bg-primary text-primary-foreground font-semibold"
                            : isAnswered
                            ? isCorrect
                              ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                              : "border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-300"
                            : "border-border bg-background text-muted-foreground"
                        )}
                      >
                        {idx + 1}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            <DialogFooter className="px-5 py-3 border-t flex justify-between items-center sm:justify-between">
              <Button
                variant="outline"
                onClick={handlePreviousQuestionDetail}
                disabled={currentQuestionDetailIndex === 0 || totalQuestionsInDialog === 0}
                size="sm"
              >
                {t('admin.papers.detailsDialog.prevQuestionButton')}
              </Button>
              <span className="text-xs font-mono text-muted-foreground">
                {totalQuestionsInDialog > 0 ? `${currentQuestionDetailIndex + 1} / ${totalQuestionsInDialog}` : ''}
              </span>
              <Button
                variant="outline"
                onClick={handleNextQuestionDetail}
                disabled={currentQuestionDetailIndex >= totalQuestionsInDialog - 1 || totalQuestionsInDialog === 0}
                size="sm"
              >
                {t('admin.papers.detailsDialog.nextQuestionButton')}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <div className="flex-grow flex items-center justify-center py-10">
            <p className="text-sm text-muted-foreground">{t('admin.papers.detailsDialog.noDetails')}</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export function PaperTable() {
  return null;
}
