
"use client";
import type { AdminBankQuestion, QuestionBankResponse } from '@/types/admin'; // Updated to QuestionBankResponse
import type { User, DifficultyLevel } from '@/types/auth';
import { fetchQuestionBankContent } from '@/lib/admin-api'; // Corrected import
import { QuestionBankManager } from '@/components/admin/question-bank-manager';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';
import React, { useEffect, useState, useCallback } from 'react';

interface AdminQuestionBankDifficultyViewProps {
  user: User | null;
  difficulty: DifficultyLevel;
}

export function AdminQuestionBankDifficultyView({ user, difficulty }: AdminQuestionBankDifficultyViewProps) {
  const { t } = useTranslation();
  const [questions, setQuestions] = useState<AdminBankQuestion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadQuestions = useCallback(async () => {
    if (!user?.token) {
      setError(t('auth.toast.sessionExpired.description'));
      setIsLoading(false);
      return;
    }
    if (!['easy', 'hybrid', 'hard'].includes(difficulty)) {
      setError(t('admin.questionBankManager.difficulty.invalid', { difficulty }));
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      // Call the corrected function and expect QuestionBankResponse
      const fetchedData: QuestionBankResponse = await fetchQuestionBankContent(user.token, difficulty);
      setQuestions(fetchedData.questions || []); // Extract questions array
      setError(null);
    } catch (e: any) {
      console.error(`Failed to load ${difficulty} question bank:`, e);
      setError(e.message || t('admin.questionBank.error.specific', { difficulty: t(`admin.questionBankManager.difficulty.${difficulty}`) }));
    } finally {
      setIsLoading(false);
    }
  }, [difficulty, user?.token, t]);

  useEffect(() => {
    loadQuestions();
  }, [loadQuestions]); 

  if (!['easy', 'hybrid', 'hard'].includes(difficulty) && !isLoading) {
     return <p>Invalid difficulty.</p>; 
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">{t('admin.questionBankManager.existing.loading')}</p>
      </div>
    );
  }

  return (
    <div className="animate-in fade-in-0 duration-500">
      {error ? (
        <Card className="shadow-lg border-destructive/50">
          <CardHeader>
            <CardTitle className="flex items-center text-destructive">
                <AlertTriangle className="mr-2 h-5 w-5"/> {t('admin.questionBank.error.title')}
            </CardTitle>
            <CardDescription>{t('admin.questionBank.error.description', { difficulty: t(`admin.questionBankManager.difficulty.${difficulty}`) })}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-destructive-foreground bg-destructive/10 p-3 rounded-md">{error}</p>
          </CardContent>
        </Card>
      ) : (
        <QuestionBankManager initialQuestions={questions} difficulty={difficulty} userToken={user?.token || null} />
      )}
    </div>
  );
}
