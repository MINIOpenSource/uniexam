"use client";

import type { AdminBankQuestion, AddQuestionPayload, QuestionBankResponse } from '@/types/admin';
import type { DifficultyLevel } from '@/types/auth';
import React, { useState, useTransition, useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { addQuestionToBank, deleteQuestionFromBank, fetchQuestionBankContent } from '@/lib/admin-api';
import { useToast } from '@/hooks/use-toast';
import { XIcon, Loader2, SearchIcon } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';

interface QuestionBankManagerProps {
  initialQuestions: AdminBankQuestion[];
  difficulty: DifficultyLevel;
  userToken: string | null;
}

const ITEMS_PER_PAGE = 10;

export function QuestionBankManager({ initialQuestions, difficulty, userToken }: QuestionBankManagerProps) {
  const { t } = useTranslation();
  const [questions, setQuestions] = useState<AdminBankQuestion[]>(initialQuestions);
  const [newQuestionBody, setNewQuestionBody] = useState('');
  const [newCorrectChoices, setNewCorrectChoices] = useState<string[]>(['']);
  const [newIncorrectChoices, setNewIncorrectChoices] = useState<string[]>(['', '', '']);

  const [isAdding, startAddTransition] = useTransition();
  const [isDeleting, startDeleteTransition] = useTransition();
  const [isRefreshing, startRefreshTransition] = useTransition();

  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const { toast } = useToast();

  const translatedDifficulty = t(`admin.questionBankManager.difficulty.${difficulty}`);

  const refreshQuestions = async () => {
    if (!userToken) {
      toast({ title: t('auth.toast.sessionExpired.title'), description: t('auth.toast.sessionExpired.description'), variant: "destructive" });
      return;
    }
    startRefreshTransition(async () => {
      try {
        const updatedBankData: QuestionBankResponse = await fetchQuestionBankContent(userToken, difficulty);
        setQuestions(updatedBankData.questions || []);
        setSearchTerm('');
        setCurrentPage(1);
        toast({ title: t('admin.questionBankManager.toast.refreshed.title'), description: t('admin.questionBankManager.toast.refreshed.description', { difficulty: translatedDifficulty }) });
      } catch (error: any) {
        toast({ title: t('admin.questionBankManager.toast.refreshError.title'), description: error.message || t('admin.questionBankManager.toast.refreshError.description'), variant: 'destructive' });
      }
    });
  };

  useEffect(() => {
    setQuestions(initialQuestions);
    setCurrentPage(1);
    setSearchTerm('');
  }, [initialQuestions]);

  const filteredQuestions = useMemo(() => {
    if (!searchTerm) {
      return questions;
    }
    return questions.filter(q =>
      q.body.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (q.correct_choices || []).some(c => c.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (q.incorrect_choices || []).some(ic => ic.toLowerCase().includes(searchTerm.toLowerCase()))
    );
  }, [questions, searchTerm]);

  const totalPages = Math.ceil(filteredQuestions.length / ITEMS_PER_PAGE);
  const paginatedQuestions = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredQuestions.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [filteredQuestions, currentPage]);

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
    setCurrentPage(1);
  };

  const handleNextPage = () => {
    if (currentPage < totalPages) {
      setCurrentPage(currentPage + 1);
    }
  };

  const handlePreviousPage = () => {
    if (currentPage > 1) {
      setCurrentPage(currentPage - 1);
    }
  };

  const handleAddCorrectChoice = () => setNewCorrectChoices([...newCorrectChoices, '']);
  const handleRemoveCorrectChoice = (index: number) => setNewCorrectChoices(newCorrectChoices.filter((_, i) => i !== index));
  const handleCorrectChoiceChange = (index: number, value: string) => {
    const updated = [...newCorrectChoices]; updated[index] = value; setNewCorrectChoices(updated);
  };

  const handleAddIncorrectChoice = () => setNewIncorrectChoices([...newIncorrectChoices, '']);
  const handleRemoveIncorrectChoice = (index: number) => setNewIncorrectChoices(newIncorrectChoices.filter((_, i) => i !== index));
  const handleIncorrectChoiceChange = (index: number, value: string) => {
    const updated = [...newIncorrectChoices]; updated[index] = value; setNewIncorrectChoices(updated);
  };

  const handleAddQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!userToken) {
      toast({ title: t('auth.toast.sessionExpired.title'), description: t('auth.toast.sessionExpired.description'), variant: "destructive" });
      return;
    }
    const trimmedCorrectChoices = newCorrectChoices.map(c => c.trim()).filter(c => c);
    const trimmedIncorrectChoices = newIncorrectChoices.map(c => c.trim()).filter(c => c);

    if (!newQuestionBody.trim()) {
      toast({ title: t('admin.questionBankManager.toast.validationError.title'), description: t('admin.questionBankManager.toast.validationError.bodyMissing'), variant: 'destructive' }); return;
    }
    if (trimmedCorrectChoices.length === 0) {
      toast({ title: t('admin.questionBankManager.toast.validationError.title'), description: t('admin.questionBankManager.toast.validationError.correctChoiceMissing'), variant: 'destructive' }); return;
    }
    if (trimmedIncorrectChoices.length === 0) {
      toast({ title: t('admin.questionBankManager.toast.validationError.title'), description: t('admin.questionBankManager.toast.validationError.incorrectChoiceMissing'), variant: 'destructive' }); return;
    }

    const payload: AddQuestionPayload = {
      body: newQuestionBody.trim(),
      question_type: 'single_choice',
      correct_choices: trimmedCorrectChoices,
      incorrect_choices: trimmedIncorrectChoices,
    };

    startAddTransition(async () => {
      try {
        await addQuestionToBank(userToken, difficulty, payload);
        toast({ title: t('admin.questionBankManager.toast.addSuccess.title'), description: t('admin.questionBankManager.toast.addSuccess.description') });
        setNewQuestionBody(''); setNewCorrectChoices(['']); setNewIncorrectChoices(['', '', '']);
        await refreshQuestions();
      } catch (error: any) {
        toast({ title: t('admin.questionBankManager.toast.addError.title'), description: error.message || t('admin.questionBankManager.toast.addError.description'), variant: 'destructive' });
      }
    });
  };

  const handleDeleteQuestion = async (questionIndexInPaginated: number) => {
    if (!userToken) {
      toast({ title: t('auth.toast.sessionExpired.title'), description: t('auth.toast.sessionExpired.description'), variant: "destructive" });
      return;
    }
    const actualQuestionObject = paginatedQuestions[questionIndexInPaginated];
    const originalIndex = questions.findIndex(q =>
      q.body === actualQuestionObject.body &&
      JSON.stringify(q.correct_choices) === JSON.stringify(actualQuestionObject.correct_choices) &&
      JSON.stringify(q.incorrect_choices) === JSON.stringify(actualQuestionObject.incorrect_choices)
    );

    if (originalIndex === -1) {
      toast({ title: "Error", description: "Could not find question to delete.", variant: "destructive" }); return;
    }

    startDeleteTransition(async () => {
      try {
        await deleteQuestionFromBank(userToken, difficulty, originalIndex);
        toast({ title: t('admin.questionBankManager.toast.deleteSuccess.title'), description: t('admin.questionBankManager.toast.deleteSuccess.description', { index: originalIndex + 1 }) });
        await refreshQuestions();
      } catch (error: any) {
        toast({ title: t('admin.questionBankManager.toast.deleteError.title'), description: error.message || t('admin.questionBankManager.toast.deleteError.description', { index: originalIndex + 1 }), variant: 'destructive' });
      }
    });
  };

  return (
    <div className="space-y-6">
      <div className="rounded border bg-card">
        <div className="px-4 py-3 border-b bg-muted/20">
          <h3 className="text-sm font-semibold">{t('admin.questionBankManager.add.title')}</h3>
        </div>
        <form onSubmit={handleAddQuestion}>
          <div className="p-4 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="questionBody" className="text-xs font-medium">{t('admin.questionBankManager.add.bodyLabel')}</Label>
              <Textarea id="questionBody" value={newQuestionBody} onChange={(e) => setNewQuestionBody(e.target.value)} placeholder={t('admin.questionBankManager.add.bodyPlaceholder')} rows={3} className="text-sm" required />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-medium">{t('admin.questionBankManager.add.correctChoicesLabel')}</Label>
              {newCorrectChoices.map((choice, index) => (
                <div key={`correct-${index}`} className="flex items-center gap-2">
                  <Input type="text" value={choice} onChange={(e) => handleCorrectChoiceChange(index, e.target.value)} placeholder={t('admin.questionBankManager.add.correctChoicePlaceholder', { index: index + 1 })} className="h-9 text-sm" required={index === 0} />
                  {newCorrectChoices.length > 1 && (
                    <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => handleRemoveCorrectChoice(index)} title={t('admin.questionBankManager.add.removeCorrectChoiceTitle')}>
                      <XIcon className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                    </Button>
                  )}
                </div>
              ))}
              <Button type="button" variant="outline" size="sm" onClick={handleAddCorrectChoice}>
                + {t('admin.questionBankManager.add.addCorrectChoice')}
              </Button>
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-medium">{t('admin.questionBankManager.add.incorrectChoicesLabel')}</Label>
              {newIncorrectChoices.map((choice, index) => (
                <div key={`incorrect-${index}`} className="flex items-center gap-2">
                  <Input type="text" value={choice} onChange={(e) => handleIncorrectChoiceChange(index, e.target.value)} placeholder={t('admin.questionBankManager.add.incorrectChoicePlaceholder', { index: index + 1 })} className="h-9 text-sm" required={index === 0} />
                  {newIncorrectChoices.length > 1 && (
                    <Button type="button" variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => handleRemoveIncorrectChoice(index)} title={t('admin.questionBankManager.add.removeIncorrectChoiceTitle')}>
                      <XIcon className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                    </Button>
                  )}
                </div>
              ))}
              <Button type="button" variant="outline" size="sm" onClick={handleAddIncorrectChoice}>
                + {t('admin.questionBankManager.add.addIncorrectChoice')}
              </Button>
            </div>
          </div>
          <div className="px-4 py-3 border-t bg-muted/10 flex justify-end">
            <Button type="submit" size="sm" disabled={isAdding || !userToken}>
              {isAdding ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> {t('admin.questionBankManager.add.submittingButton')}</> : t('admin.questionBankManager.add.submitButton')}
            </Button>
          </div>
        </form>
      </div>

      <div className="rounded border bg-card">
        <div className="px-4 py-3 border-b bg-muted/20 flex flex-col sm:flex-row justify-between sm:items-center gap-2">
          <h3 className="text-sm font-semibold">{t('admin.questionBankManager.existing.title', { count: filteredQuestions.length })}</h3>
          <div className="flex items-center gap-2">
            <div className="relative flex-1 sm:w-64">
              <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input type="search" placeholder={t('admin.questionBankManager.search.placeholder')} value={searchTerm} onChange={handleSearchChange} className="pl-8 h-8 text-xs w-full" />
            </div>
            <Button onClick={refreshQuestions} variant="outline" size="sm" className="h-8 text-xs" disabled={isRefreshing || isAdding || isDeleting || !userToken}>
              {isRefreshing && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              {t('admin.questionBankManager.existing.refreshButton')}
            </Button>
          </div>
        </div>
        <div className="p-4">
          {isRefreshing && paginatedQuestions.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
              <Loader2 className="h-5 w-5 mr-2 animate-spin" /> {t('admin.questionBankManager.existing.loading')}
            </div>
          ) : !isRefreshing && paginatedQuestions.length === 0 && searchTerm ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              <p>{t('admin.questionBankManager.existing.noResults.title')}</p>
            </div>
          ) : !isRefreshing && paginatedQuestions.length === 0 && !searchTerm ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              <p>{t('admin.questionBankManager.existing.empty.title')}</p>
            </div>
          ) : (
            <>
              <div className="space-y-3">
                {paginatedQuestions.map((q, localIndex) => {
                  const originalQuestionIndex = questions.findIndex(origQ => origQ.body === q.body && JSON.stringify(origQ.correct_choices) === JSON.stringify(q.correct_choices) && JSON.stringify(origQ.incorrect_choices) === JSON.stringify(q.incorrect_choices));
                  return (
                    <div key={originalQuestionIndex !== -1 ? originalQuestionIndex : localIndex} className="rounded border bg-background p-3.5 space-y-2">
                      <div className="flex justify-between items-start gap-2">
                        <p className="text-sm font-medium break-words">
                          <span className="font-mono mr-1.5">{(currentPage - 1) * ITEMS_PER_PAGE + localIndex + 1}.</span>
                          {q.body}
                        </p>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button variant="outline" size="sm" className="h-7 text-xs text-destructive hover:text-destructive shrink-0" disabled={isDeleting || !userToken}>
                              {t('admin.questionBankManager.deleteDialog.delete')}
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>{t('admin.questionBankManager.deleteDialog.title')}</AlertDialogTitle>
                              <AlertDialogDescription>{t('admin.questionBankManager.deleteDialog.description', { index: originalQuestionIndex + 1, body: q.body.substring(0, 50) })}</AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel disabled={isDeleting}>{t('admin.questionBankManager.deleteDialog.cancel')}</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleDeleteQuestion(localIndex)} disabled={isDeleting || originalQuestionIndex === -1 || !userToken} className="bg-destructive hover:bg-destructive/90">
                                {isDeleting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> {t('admin.questionBankManager.deleteDialog.deleting')}</> : t('admin.questionBankManager.deleteDialog.delete')}
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                      <div className="text-xs space-y-1 pt-1 border-t">
                        {(q.correct_choices || []).map((choice, cIdx) => (
                          <div key={`correct-${originalQuestionIndex}-${cIdx}`} className="flex items-start gap-1.5">
                            <span className="font-mono text-emerald-600 dark:text-emerald-400 shrink-0">[✓]</span>
                            <span className="break-words">{choice}</span>
                          </div>
                        ))}
                        {(q.incorrect_choices || []).map((choice, icIdx) => (
                          <div key={`incorrect-${originalQuestionIndex}-${icIdx}`} className="flex items-start gap-1.5">
                            <span className="font-mono text-red-600 dark:text-red-400 shrink-0">[✗]</span>
                            <span className="break-words text-muted-foreground">{choice}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4 pt-3 border-t">
                  <Button variant="outline" size="sm" onClick={handlePreviousPage} disabled={currentPage === 1 || isAdding || isDeleting || isRefreshing}>
                    {t('admin.questionBankManager.pagination.previous')}
                  </Button>
                  <span className="text-xs font-mono text-muted-foreground">
                    {currentPage} / {totalPages}
                  </span>
                  <Button variant="outline" size="sm" onClick={handleNextPage} disabled={currentPage === totalPages || isAdding || isDeleting || isRefreshing}>
                    {t('admin.questionBankManager.pagination.next')}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
