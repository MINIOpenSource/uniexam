"use client";
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/hooks/useTranslation';
import type { DifficultyLevel } from '@/types/auth';

interface AdminQuestionBanksHomeViewProps {
  onNavigateToDifficulty: (difficulty: DifficultyLevel) => void;
}

export function AdminQuestionBanksHomeView({ onNavigateToDifficulty }: AdminQuestionBanksHomeViewProps) {
  const { t } = useTranslation();

  type DifficultyItem = {
    nameKey: 'admin.questionBanks.easy.title' | 'admin.questionBanks.hybrid.title' | 'admin.questionBanks.hard.title';
    difficulty: DifficultyLevel;
    buttonKey: 'admin.questionBanks.easy.button' | 'admin.questionBanks.hybrid.button' | 'admin.questionBanks.hard.button';
  };

  const difficulties: Array<DifficultyItem> = [
    { nameKey: 'admin.questionBanks.easy.title', difficulty: 'easy', buttonKey: 'admin.questionBanks.easy.button' },
    { nameKey: 'admin.questionBanks.hybrid.title', difficulty: 'hybrid', buttonKey: 'admin.questionBanks.hybrid.button' },
    { nameKey: 'admin.questionBanks.hard.title', difficulty: 'hard', buttonKey: 'admin.questionBanks.hard.button' },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {difficulties.map((item) => (
        <div key={item.difficulty} className="flex flex-col justify-between rounded border bg-card p-4">
          <div className="mb-3 font-medium text-sm text-foreground">
            {t(item.nameKey)}
          </div>
          <Button variant="outline" size="sm" className="w-full" onClick={() => onNavigateToDifficulty(item.difficulty)}>
            {t(item.buttonKey)}
          </Button>
        </div>
      ))}
    </div>
  );
}
