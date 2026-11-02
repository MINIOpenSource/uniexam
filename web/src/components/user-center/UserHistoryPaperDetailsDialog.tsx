"use client";

import type { HistoryPaperDetailResponse, HistoryPaperQuestionClientView } from '@/types/auth';
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
import { cn } from '@/lib/utils';
import { useTranslation } from '@/hooks/useTranslation';
import { CopyButton } from '@/components/ui/copy-button';
import { AntiOcrSurface, AntiOcrText, prefetchObfuscatedFont, useExternalObfuscatedFont } from '@/components/exam/anti-ocr-text';

interface UserHistoryPaperDetailsDialogProps {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  selectedPaperDetails: HistoryPaperDetailResponse | null;
  isLoadingDetails: boolean;
}

const OPTION_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

export function UserHistoryPaperDetailsDialog({
  isOpen,
  onOpenChange,
  selectedPaperDetails,
  isLoadingDetails,
}: UserHistoryPaperDetailsDialogProps) {
  const { t } = useTranslation();
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const questionNavScrollContainerRef = useRef<HTMLDivElement>(null);
  const questionButtonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (isOpen && selectedPaperDetails) {
      setCurrentQuestionIndex(0);
      questionButtonRefs.current = Array(selectedPaperDetails.paper_questions?.length || 0).fill(null);
    }
  }, [isOpen, selectedPaperDetails]);

  useEffect(() => {
    if (isOpen && selectedPaperDetails && selectedPaperDetails.paper_questions && selectedPaperDetails.paper_questions.length > 0) {
      const activeButtonElement = questionButtonRefs.current[currentQuestionIndex];
      if (activeButtonElement && questionNavScrollContainerRef.current) {
        activeButtonElement.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
          inline: 'center',
        });
      }
    }
  }, [currentQuestionIndex, isOpen, selectedPaperDetails]);

  const handleNextQuestionDetail = () => {
    if (selectedPaperDetails && selectedPaperDetails.paper_questions && currentQuestionIndex < selectedPaperDetails.paper_questions.length - 1) {
      setCurrentQuestionIndex(prev => prev + 1);
    }
  };

  const handlePreviousQuestionDetail = () => {
    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex(prev => prev - 1);
    }
  };

  const totalQuestionsInDialog = selectedPaperDetails?.paper_questions?.length || 0;
  const currentQuestionForDialog: HistoryPaperQuestionClientView | undefined = selectedPaperDetails?.paper_questions?.[currentQuestionIndex];
  const scopeId = `ue-hs-${currentQuestionIndex}`;

  const obfFontFamily = React.useMemo(() => {
    if (!currentQuestionForDialog?.obfuscated_font) return undefined;
    const tail = currentQuestionForDialog.obfuscated_font.slice(-16).replace(/[^a-zA-Z0-9]/g, '');
    return `UEObfHist_${currentQuestionIndex}_${tail}`;
  }, [currentQuestionForDialog?.obfuscated_font, currentQuestionIndex]);

  const { domPermutedHistoryChoices, historyOrderCss } = React.useMemo(() => {
    const rawEntries = currentQuestionForDialog?.choices ? Object.entries(currentQuestionForDialog.choices) : [];
    const items = rawEntries.map(([choiceId, choiceText], visualIndex) => {
      const slotClass = `ue-hopt-s-${currentQuestionIndex}-${choiceId.slice(0, 8)}`;
      let h = 2166136261;
      const seedStr = `h:${currentQuestionIndex}:${choiceId}`;
      for (let i = 0; i < seedStr.length; i++) {
        h ^= seedStr.charCodeAt(i);
        h = Math.imul(h, 16777619);
      }
      const sortWeight = h >>> 0;
      const nestDepth = sortWeight % 3;
      return { choiceId, choiceText, visualIndex, slotClass, nestDepth, sortWeight };
    });

    const cssLines = items.map(
      (it) => `.${scopeId} .${it.slotClass} { order: ${it.visualIndex + 1}; }`
    );
    const permuted = [...items].sort((a, b) => a.sortWeight - b.sortWeight);
    if (permuted.length > 1 && permuted.every((it, idx) => it.visualIndex === idx)) {
      const first = permuted.shift()!;
      permuted.push(first);
    }
    return {
      domPermutedHistoryChoices: permuted,
      historyOrderCss: cssLines.join("\n"),
    };
  }, [currentQuestionForDialog?.choices, currentQuestionIndex, scopeId]);

  const isFontReady = useExternalObfuscatedFont(currentQuestionForDialog?.obfuscated_font, obfFontFamily, scopeId, historyOrderCss);

  useEffect(() => {
    if (!isOpen || !selectedPaperDetails?.paper_questions) return;
    const list = selectedPaperDetails.paper_questions;
    const neighbors = [currentQuestionIndex + 1, currentQuestionIndex + 2, currentQuestionIndex - 1];
    const timer = setTimeout(() => {
      for (const idx of neighbors) {
        if (idx >= 0 && idx < list.length) {
          const q = list[idx];
          if (q?.obfuscated_font) {
            const tail = q.obfuscated_font.slice(-16).replace(/[^a-zA-Z0-9]/g, '');
            prefetchObfuscatedFont(q.obfuscated_font, `UEObfHist_${idx}_${tail}`);
          }
        }
      }
    }, 60);
    return () => clearTimeout(timer);
  }, [isOpen, currentQuestionIndex, selectedPaperDetails?.paper_questions]);

  const preventCopyAction = React.useCallback((e: React.SyntheticEvent) => {
    e.preventDefault();
  }, []);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] flex flex-col p-0">
        <DialogHeader className="px-5 py-3.5 border-b">
          <DialogTitle className="flex items-center gap-1.5 text-sm font-semibold">
            <span>{t('userHistory.detailsDialog.titlePrefix')}</span>
            <span className="font-mono">{selectedPaperDetails?.paper_id || '...'}</span>
            {selectedPaperDetails?.paper_id && (
              <CopyButton textToCopy={selectedPaperDetails.paper_id} toastMessageKey="copyButton.toast.success.paperIdCopied" size="sm" className="p-0.5 h-5 w-5" iconClassName="h-3 w-3" title={t('copyButton.copy')} />
            )}
          </DialogTitle>
        </DialogHeader>

        {isLoadingDetails ? (
          <div className="flex-grow flex items-center justify-center py-12 text-xs text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            <span>{t('userHistory.detailsDialog.loading')}</span>
          </div>
        ) : selectedPaperDetails && currentQuestionForDialog ? (
          <>
            <ScrollArea className="flex-grow px-5 py-4 min-h-0">
              {!isFontReady ? (
                <div className="rounded border bg-card p-6 flex items-center justify-center gap-2 text-xs text-muted-foreground select-none">
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                  <span className="font-sans">正在加载受保护题目字库...</span>
                </div>
              ) : (
              <AntiOcrSurface
                scopeId={scopeId}
                className="rounded border bg-card p-4 space-y-3 select-none"
              >
                <div
                  className="space-y-3"
                  onCopy={preventCopyAction}
                  onCut={preventCopyAction}
                  onContextMenu={preventCopyAction}
                >
                  <p className="text-sm font-medium break-words">
                    <span className="mr-1.5 font-mono text-muted-foreground">{currentQuestionIndex + 1}.</span>
                    <AntiOcrText
                      text={currentQuestionForDialog.body}
                      seedKey={`hist-${currentQuestionIndex}-body`}
                    />
                  </p>
                  <div className="ue-opt-group text-xs">
                    {domPermutedHistoryChoices.map((item) => {
                      const isSubmitted = currentQuestionForDialog.submitted_answer === item.choiceId;
                      const rowNode = (
                        <div
                          key={item.choiceId}
                          className={cn(
                            item.slotClass,
                            "flex items-center justify-between gap-2 rounded border px-3 py-2 break-words",
                            isSubmitted
                              ? "border-primary bg-primary/10 font-medium"
                              : "border-border bg-background"
                          )}
                        >
                          <div className="flex items-center gap-2.5">
                            <span
                              className={cn(
                                "inline-flex h-3 w-3 shrink-0 rounded-full border",
                                isSubmitted
                                  ? "border-primary bg-primary"
                                  : "border-muted-foreground/50 bg-background"
                              )}
                            />
                            <span>
                              <AntiOcrText
                                text={item.choiceText}
                                seedKey={`hist-${currentQuestionIndex}-opt-${item.choiceId}`}
                              />
                            </span>
                          </div>
                          {isSubmitted && (
                            <span className="font-sans rounded border border-primary/40 bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary shrink-0">
                              {t('userHistory.detailsDialog.submittedAnswerBadge')}
                            </span>
                          )}
                        </div>
                      );

                      if (item.nestDepth === 2) {
                        return (
                          <div key={`hw2-${item.choiceId}`} className="ue-opt-nest">
                            <section className="ue-opt-nest">{rowNode}</section>
                          </div>
                        );
                      }
                      if (item.nestDepth === 1) {
                        return (
                          <div key={`hw1-${item.choiceId}`} className="ue-opt-nest">
                            {rowNode}
                          </div>
                        );
                      }
                      return rowNode;
                    })}
                  </div>
                  {(currentQuestionForDialog.submitted_answer === null || currentQuestionForDialog.submitted_answer === "-1") && (
                    <p className="text-xs text-muted-foreground">{t('userHistory.detailsDialog.notAnswered')}</p>
                  )}
                </div>
              </AntiOcrSurface>
              )}
            </ScrollArea>

            {totalQuestionsInDialog > 0 && (
              <div className="question-nav-scrollbar w-full border-t border-b bg-muted/20 overflow-x-auto px-5 py-2">
                <div ref={questionNavScrollContainerRef} className="flex flex-wrap gap-1.5">
                  {selectedPaperDetails.paper_questions?.map((q, idx) => {
                    const isCurrent = idx === currentQuestionIndex;
                    const isAnswered = q.submitted_answer !== null && q.submitted_answer !== "-1";

                    return (
                      <button
                        key={`nav-user-hist-${idx}`}
                        type="button"
                        ref={el => { questionButtonRefs.current[idx] = el; }}
                        onClick={() => setCurrentQuestionIndex(idx)}
                        title={t('userHistory.detailsDialog.jumpToQuestion', { index: idx + 1 })}
                        className={cn(
                          "h-7 min-w-[2rem] px-1.5 rounded border text-xs font-mono",
                          isCurrent
                            ? "border-primary bg-primary text-primary-foreground"
                            : isAnswered
                            ? "border-primary/40 bg-primary/10 text-foreground"
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

            <DialogFooter className="px-5 py-3 flex justify-between items-center">
              <Button
                variant="outline"
                onClick={handlePreviousQuestionDetail}
                disabled={currentQuestionIndex === 0 || totalQuestionsInDialog === 0}
                size="sm"
              >
                {t('userHistory.detailsDialog.prevButton')}
              </Button>
              <span className="text-xs font-mono text-muted-foreground">
                {totalQuestionsInDialog > 0 ? t('userHistory.detailsDialog.questionIndicator', { current: currentQuestionIndex + 1, total: totalQuestionsInDialog }) : ''}
              </span>
              <Button
                variant="outline"
                onClick={handleNextQuestionDetail}
                disabled={currentQuestionIndex >= totalQuestionsInDialog - 1 || totalQuestionsInDialog === 0}
                size="sm"
              >
                {t('userHistory.detailsDialog.nextButton')}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <div className="flex-grow flex items-center justify-center py-12 text-xs text-muted-foreground">
            <span>{t('userHistory.detailsDialog.noDetails')}</span>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
