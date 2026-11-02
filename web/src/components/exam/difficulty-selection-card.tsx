"use client";

import * as React from 'react';
import type { Difficulty } from '@/types/exam';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';
import { cn } from '@/lib/utils';

interface DifficultySelectionCardProps {
  onSelectDifficulty: (difficulty: Difficulty) => void;
  isLoading: boolean;
}

export function DifficultySelectionCard({
  onSelectDifficulty,
  isLoading,
}: DifficultySelectionCardProps) {
  const { t } = useTranslation();
  const currentBrandName = t('app.brandName');
  const [currentSelectedDifficulty, setCurrentSelectedDifficulty] = React.useState<Difficulty | null>(null);

  const difficultyOptions: Array<{
    value: Difficulty;
    labelKey: 'difficulty.easy.label' | 'difficulty.hybrid.label' | 'difficulty.hard.label';
    descriptionKey: 'difficulty.easy.description' | 'difficulty.hybrid.description' | 'difficulty.hard.description';
  }> = [
    { value: 'easy', labelKey: 'difficulty.easy.label', descriptionKey: 'difficulty.easy.description' },
    { value: 'hybrid', labelKey: 'difficulty.hybrid.label', descriptionKey: 'difficulty.hybrid.description' },
    { value: 'hard', labelKey: 'difficulty.hard.label', descriptionKey: 'difficulty.hard.description' },
  ];

  const handleConfirmNewExam = () => {
    if (currentSelectedDifficulty) {
      onSelectDifficulty(currentSelectedDifficulty);
    }
  };

  return (
    <div className="w-full space-y-4">
      <div className="space-y-2">
        {difficultyOptions.map((option) => {
          const isSelected = currentSelectedDifficulty === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => setCurrentSelectedDifficulty(option.value)}
              disabled={isLoading}
              aria-pressed={isSelected}
              className={cn(
                "w-full rounded border px-3.5 py-2.5 text-left transition-colors",
                isSelected
                  ? "border-primary bg-primary/10"
                  : "border-border bg-background hover:bg-muted/50"
              )}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-foreground">
                  {t(option.labelKey)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {t(option.descriptionKey, { brandName: currentBrandName })}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      <div className="flex justify-end border-t pt-3">
        <Button
          onClick={handleConfirmNewExam}
          disabled={isLoading || !currentSelectedDifficulty}
          size="sm"
        >
          {isLoading && currentSelectedDifficulty ? (
            <>
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              {t('difficulty.selection.loadingButton')}
            </>
          ) : (
            t('difficulty.selection.confirmButton')
          )}
        </Button>
      </div>
    </div>
  );
}
