"use client";

import * as React from 'react';
import type { Paper } from '@/types/exam';
import { QuestionCard } from './question-card';
import { prefetchObfuscatedFont, type WsFontPaperContext } from './anti-ocr-text';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';
import { cn } from '@/lib/utils';

export type QuestionNavigationDirection = 'initial' | 'next' | 'previous';

const formatTimeDisplay = (ms: number): string => {
  if (ms < 0) ms = 0;
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

interface QuestionTimerProps {
  currentQuestionIndex: number;
  accumulatedMsRef: React.MutableRefObject<number[]>;
  activeStartRef: React.MutableRefObject<number>;
}

const QuestionTimer = React.memo(function QuestionTimer({
  currentQuestionIndex,
  accumulatedMsRef,
  activeStartRef,
}: QuestionTimerProps) {
  const { t } = useTranslation();
  const [displayedTime, setDisplayedTime] = React.useState<string>("00:00");

  React.useEffect(() => {
    const updateDisplay = () => {
      const elapsed = (accumulatedMsRef.current[currentQuestionIndex] || 0) + (Date.now() - activeStartRef.current);
      setDisplayedTime(formatTimeDisplay(elapsed));
    };
    updateDisplay();
    const intervalId = setInterval(updateDisplay, 1000);
    return () => clearInterval(intervalId);
  }, [currentQuestionIndex, accumulatedMsRef, activeStartRef]);

  return (
    <span className="font-mono">
      {t('exam.timer.currentQuestion', { time: displayedTime })}
    </span>
  );
});

interface ExamFormProps {
  paperData: Paper;
  currentQuestionIndex: number;
  answers: (string | null)[];
  onAnswerChange: (questionIndex: number, choiceId: string) => void;
  onQuestionIndexChange: (newIndex: number) => void;
  onTriggerSubmit: () => void;
  isSubmitting: boolean;
  brandName: string;
}

export function ExamForm({
  paperData,
  currentQuestionIndex,
  answers,
  onAnswerChange,
  onQuestionIndexChange,
  onTriggerSubmit,
  isSubmitting,
}: ExamFormProps) {
  const { t } = useTranslation();
  const totalQuestions = paperData.paper.length;

  const accumulatedMsRef = React.useRef<number[]>(Array(totalQuestions).fill(0));
  const activeStartRef = React.useRef<number>(Date.now());
  const prevQuestionIndexRef = React.useRef<number>(currentQuestionIndex);

  React.useEffect(() => {
    if (accumulatedMsRef.current.length !== totalQuestions) {
      accumulatedMsRef.current = Array(totalQuestions).fill(0);
    }
  }, [totalQuestions]);

  const wsFontContext = React.useMemo<WsFontPaperContext>(
    () => ({
      paperId: paperData.paper_id,
      paper: paperData.paper,
      paperHash: paperData.paper_hash,
    }),
    [paperData.paper_id, paperData.paper, paperData.paper_hash]
  );

  React.useEffect(() => {
    const prevIdx = prevQuestionIndexRef.current;
    if (prevIdx !== currentQuestionIndex) {
      const spent = Date.now() - activeStartRef.current;
      accumulatedMsRef.current[prevIdx] = (accumulatedMsRef.current[prevIdx] || 0) + spent;
      activeStartRef.current = Date.now();
      prevQuestionIndexRef.current = currentQuestionIndex;
    }

    // Background prefetch of adjacent questions (+1, +2, -1) over WebSocket so Next/Previous switches are instant
    const neighbors = [currentQuestionIndex + 1, currentQuestionIndex + 2, currentQuestionIndex - 1];
    const timer = setTimeout(() => {
      for (const idx of neighbors) {
        if (idx >= 0 && idx < totalQuestions && wsFontContext.paperId) {
          const rawKey = wsFontContext.paperHash || wsFontContext.paperId || 'ws';
          const tail = rawKey.slice(-16).replace(/[^a-zA-Z0-9]/g, '');
          prefetchObfuscatedFont(undefined, `UEObfQ_${idx}_${tail}`, wsFontContext, idx);
        }
      }
    }, 60);
    return () => clearTimeout(timer);
  }, [currentQuestionIndex, totalQuestions, wsFontContext]);

  const handleLocalAnswerChange = React.useCallback(
    (qIndex: number, choiceId: string) => {
      onAnswerChange(qIndex, choiceId);
    },
    [onAnswerChange]
  );

  const handleNavigate = React.useCallback(
    (newIndex: number) => {
      if (newIndex >= 0 && newIndex < totalQuestions && newIndex !== currentQuestionIndex) {
        onQuestionIndexChange(newIndex);
      }
    },
    [totalQuestions, currentQuestionIndex, onQuestionIndexChange]
  );

  const handlePreviousQuestion = React.useCallback(() => {
    if (currentQuestionIndex > 0) {
      handleNavigate(currentQuestionIndex - 1);
    }
  }, [currentQuestionIndex, handleNavigate]);

  const handleNextQuestion = React.useCallback(() => {
    if (currentQuestionIndex < totalQuestions - 1) {
      handleNavigate(currentQuestionIndex + 1);
    }
  }, [currentQuestionIndex, totalQuestions, handleNavigate]);

  const answeredQuestionsCount = React.useMemo(
    () => answers.filter(a => a !== null && a !== "-1").length,
    [answers]
  );

  if (totalQuestions === 0) {
    return (
      <div className="container mx-auto max-w-3xl py-8 px-4 text-center text-sm text-muted-foreground">
        {t('examForm.emptyPaper')}
      </div>
    );
  }

  const currentQuestion = paperData.paper[currentQuestionIndex];
  const isFirstQuestion = currentQuestionIndex === 0;
  const isLastQuestion = currentQuestionIndex === totalQuestions - 1;

  return (
    <div className="flex flex-col flex-grow w-full max-w-3xl mx-auto px-3 sm:px-4 py-4 gap-3">
      <div className="rounded border bg-card p-3 space-y-2.5" data-ue-zone="question_nav">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            {t('exam.progress.completed', { count: answeredQuestionsCount })} / {t('exam.progress.remaining', { count: totalQuestions - answeredQuestionsCount })}
          </span>
          <QuestionTimer
            currentQuestionIndex={currentQuestionIndex}
            accumulatedMsRef={accumulatedMsRef}
            activeStartRef={activeStartRef}
          />
          <span className="font-medium text-foreground">
            {t('exam.questionLabel', { current: currentQuestionIndex + 1, total: totalQuestions })}
          </span>
        </div>

        <div className="w-full border-t pt-2.5">
          <div className="flex flex-wrap gap-1.5">
            {paperData.paper.map((_, index) => {
              const isCurrent = currentQuestionIndex === index;
              const isAnswered = answers[index] !== null && answers[index] !== "-1";

              return (
                <button
                  key={`nav-${index}`}
                  type="button"
                  onClick={() => handleNavigate(index)}
                  title={t('exam.jumpToQuestion', { index: index + 1 })}
                  className={cn(
                    "h-7 min-w-[2rem] px-1.5 rounded border text-xs font-mono transition-colors",
                    isCurrent
                      ? "border-primary bg-primary text-primary-foreground font-semibold"
                      : isAnswered
                      ? "border-emerald-600/50 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/20"
                      : "border-border bg-background text-muted-foreground hover:bg-muted"
                  )}
                >
                  {index + 1}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex-grow">
        <QuestionCard
          question={currentQuestion}
          questionIndex={currentQuestionIndex}
          selectedAnswer={answers[currentQuestionIndex]}
          onAnswerChange={handleLocalAnswerChange}
          wsFontContext={wsFontContext}
        />
      </div>

      <div className="flex items-center justify-between gap-2 rounded border bg-card px-4 py-3" data-ue-zone="exam_actions">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            onClick={handlePreviousQuestion}
            disabled={isFirstQuestion || isSubmitting}
            variant="outline"
            size="sm"
          >
            {t('exam.button.previous')}
          </Button>
          <Button
            type="button"
            onClick={handleNextQuestion}
            disabled={isLastQuestion || isSubmitting}
            variant="outline"
            size="sm"
          >
            {t('exam.button.next')}
          </Button>
        </div>

        <Button
          type="button"
          onClick={onTriggerSubmit}
          disabled={isSubmitting}
          size="sm"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              {t('exam.button.submitting')}
            </>
          ) : (
            t('exam.button.submit')
          )}
        </Button>
      </div>
    </div>
  );
}
