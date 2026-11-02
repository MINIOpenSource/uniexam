
"use client"; // This page now needs to be a client component
import type { AdminBankQuestion, QuestionBankResponse } from '@/types/admin'; // Updated to QuestionBankResponse
import { fetchQuestionBankContent } from '@/lib/admin-api'; // Updated import
import { QuestionBankManager } from '@/components/admin/question-bank-manager';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { notFound } from 'next/navigation';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';
import React, { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import type { DifficultyLevel } from '@/types/auth';

type DifficultyPageProps = {
  params: {
    difficulty: string;
  };
};

export default function DifficultyBankPage({ params }: DifficultyPageProps) {
  const { t } = useTranslation();
  const { user, isLoading: authIsLoading } = useAuth();
  const difficulty = params.difficulty as DifficultyLevel;

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
      notFound();
      return;
    }
    setIsLoading(true);
    try {
      // fetchQuestionBank was renamed to fetchQuestionBankContent and returns QuestionBankResponse
      const fetchedData: QuestionBankResponse = await fetchQuestionBankContent(user.token, difficulty);
      setQuestions(fetchedData.questions || []); // Extract questions from the response
      setError(null);
    } catch (e: any) {
      console.error(`Failed to load ${difficulty} question bank:`, e);
      setError(e.message || t('admin.questionBank.error.specific', { difficulty: t(`admin.questionBankManager.difficulty.${difficulty}`) }));
    } finally {
      setIsLoading(false);
    }
  }, [difficulty, user?.token, t]); 

  useEffect(() => {
    if (user?.token && !authIsLoading) {
        loadQuestions();
    } else if (!user?.token && !authIsLoading) {
        setError(t('auth.toast.sessionExpired.description'));
        setIsLoading(false);
    }
  }, [user?.token, authIsLoading, loadQuestions]);

  if (!['easy', 'hybrid', 'hard'].includes(difficulty) && !isLoading) {
    notFound();
  }

  if (authIsLoading && isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">{t('admin.questionBankManager.existing.loading')}</p>
      </div>
    );
  }

  return (
    <div className="animate-in fade-in-0 duration-500">
      {isLoading ? (
         <div className="flex flex-col items-center justify-center py-20 text-center">
            <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">{t('admin.questionBankManager.existing.loading')}</p>
        </div>
      ) : error ? (
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
        <QuestionBankManager initialQuestions={questions} difficulty={difficulty} userToken={user?.token || null}/>
      )}
    </div>
  );
}
