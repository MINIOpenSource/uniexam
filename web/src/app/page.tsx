"use client";

import * as React from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import type { Paper, Submission, FinishApiResponse, ResultPageDisplayData, ExamState, Difficulty, UpdateApiResponse, AutoSaveStatus, ExamQuestion } from '@/types/exam';
import type { TranslationKeys } from '@/hooks/useTranslation';
import type { HistoryItem, HistoryPaperDetailResponse, DifficultyLevel } from '@/types/auth';

import { ExamForm } from '@/components/exam/exam-form';
import { ResultPage } from '@/components/exam/result-page';
import { DifficultySelectionCard } from '@/components/exam/difficulty-selection-card';
import { Button } from '@/components/ui/button';
import { Loader2, SearchIcon } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { UnansweredConfirmationCard } from '@/components/exam/unanswered-confirmation-card';
import { UserCenterExamCard } from '@/components/user-center/UserCenterExamCard';
import { UserHistoryPaperDetailsDialog } from '@/components/user-center/UserHistoryPaperDetailsDialog';
import { MultiDeviceDialog } from '@/components/exam/multi-device-dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/hooks/useTranslation';
import { useSettings } from '@/context/SettingsContext';
import { ExamInfoBar } from '@/components/exam/exam-info-bar';
import { useToast } from '@/hooks/use-toast';
import { CopyButton } from "@/components/ui/copy-button";
import { fetchExamPaper, updateExamProgress, finishExamSubmission, fetchUserHistory, fetchHistoryPaperDetails } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { useExamWebSocket } from '@/hooks/useExamWebSocket';
import { ThemeToggle } from '@/components/settings/theme-toggle';
import { LanguageToggle } from '@/components/settings/language-toggle';

import { AdminSidebar, type AdminSectionId } from '@/components/admin_views/AdminSidebar';
import { AdminHomeView } from '@/components/admin_views/AdminHomeView';
import { AdminLiveMonitorView } from '@/components/admin_views/AdminLiveMonitorView';
import { AdminPapersView } from '@/components/admin_views/AdminPapersView';
import { AdminQuestionBanksHomeView } from '@/components/admin_views/AdminQuestionBanksHomeView';
import { AdminQuestionBankDifficultyView } from '@/components/admin_views/AdminQuestionBankDifficultyView';
import { AdminUsersView } from '@/components/admin_views/AdminUsersView';
import { AdminSettingsView } from '@/components/admin_views/AdminSettingsView';
import { useSecurityShield } from '@/components/security/security-shield';
import { SidebarProvider, SidebarTrigger, SidebarInset } from '@/components/ui/sidebar';
import { useIsMobile } from '@/hooks/use-mobile';
import Link from 'next/link';

const formatTimeDisplay = (ms: number): string => {
  if (ms < 0) ms = 0;
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

const debounce = <F extends (...args: any[]) => any>(func: F, waitFor: number) => {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  const debounced = (...args: Parameters<F>) => {
    if (timeout !== null) { clearTimeout(timeout); timeout = null; }
    timeout = setTimeout(() => func(...args), waitFor);
  };
  return debounced as (...args: Parameters<F>) => ReturnType<F>;
};

function mapSelectedTextsToLocalUuids(
  questions: ExamQuestion[],
  selectedTexts: (string | null)[],
  fallbackAnswers: (string | null)[]
): (string | null)[] {
  return questions.map((q, idx) => {
    const targetText = selectedTexts[idx];
    if (targetText === null || targetText === undefined || targetText === '') {
      return null;
    }
    const choices = q.choices || {};
    for (const [optUuid, optText] of Object.entries(choices)) {
      if (optText === targetText) {
        return optUuid;
      }
    }
    return fallbackAnswers[idx] ?? null;
  });
}

type ConfirmActionInfo = {
  type: 'resume' | 'difficulty'; messageKey: TranslationKeys; messageParams?: Record<string, string>; paperId?: string; difficulty?: Difficulty; action: () => void;
} | null;

type PendingInstantStartInfo = { type: 'resume' | 'difficulty'; paperId?: string; difficulty?: Difficulty; } | null;

type UserStatusFilter = 'all' | 'PASSED' | 'FAILED' | 'IN_PROGRESS';
type UserDifficultyFilter = 'all' | Difficulty;

function ExamPageContent() {
  const { t } = useTranslation();
  const { settings } = useSettings();
  const { toast } = useToast();
  const searchParams = useSearchParams();
  const { user, isAdmin, isLoading: authIsLoading, refreshToken, logout } = useAuth();
  const router = useRouter();
  const isMobile = useIsMobile();

  const currentBrandName = settings.brandName || t('app.brandName');

  const [pageMode, setPageMode] = React.useState<'user_center' | 'exam_active_direct' | 'admin_panel'>('user_center');
  const [adminSelectedSection, setAdminSelectedSection] = React.useState<AdminSectionId>('home');
  const [adminSelectedDifficultyBank, setAdminSelectedDifficultyBank] = React.useState<DifficultyLevel | null>(null);
  const [adminPaperUpdateVersion, setAdminPaperUpdateVersion] = React.useState(0);
  const { domPurgedByDebugger, config: shieldConfig, events: shieldEvents } = useSecurityShield();

  const [showDifficultyModal, setShowDifficultyModal] = React.useState(false);
  const [examState, setExamState] = React.useState<ExamState>('authenticating');
  const [selectedDifficulty, setSelectedDifficulty] = React.useState<Difficulty | null>(null);
  const [paperData, setPaperData] = React.useState<Paper | null>(null);
  const [resultData, setResultData] = React.useState<ResultPageDisplayData | null>(null);
  const [examStartTime, setExamStartTime] = React.useState<Date | null>(null);
  const [totalElapsedTime, setTotalElapsedTime] = React.useState<string>("00:00");
  const [currentQuestionIndex, setCurrentQuestionIndex] = React.useState(0);
  const [answers, setAnswers] = React.useState<(string | null)[]>([]);
  const [unansweredSubmissionSummary, setUnansweredSubmissionSummary] = React.useState<{ indices: number[]; paperId: string; submission: Submission } | null>(null);
  const [autoSaveStatus, setAutoSaveStatus] = React.useState<AutoSaveStatus>('idle');
  const [confirmActionInfo, setConfirmActionInfo] = React.useState<ConfirmActionInfo | null>(null);
  const [pendingInstantStartInfo, setPendingInstantStartInfo] = React.useState<PendingInstantStartInfo | null>(null);
  const [examHistory, setExamHistory] = React.useState<HistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = React.useState(true);
  const [historyError, setHistoryError] = React.useState<string | null>(null);
  const [searchTermUser, setSearchTermUser] = React.useState('');
  const [statusFilterUser, setStatusFilterUser] = React.useState<UserStatusFilter>('all');
  const [difficultyFilterUser, setDifficultyFilterUser] = React.useState<UserDifficultyFilter>('all');
  const wasUrlInitiatedRef = React.useRef(false);
  const shownUrlInitiatedToastRef = React.useRef(false);
  const initialUrlParamsProcessedRef = React.useRef(false);
  const lastProcessedUrlQueryRef = React.useRef<string | null>(null);
  const isMountedRef = React.useRef(false);
  const [adminSidebarOpen, setAdminSidebarOpen] = React.useState(!isMobile);

  const [isHistoryDetailsModalOpen, setIsHistoryDetailsModalOpen] = React.useState(false);
  const [selectedHistoryPaperDetails, setSelectedHistoryPaperDetails] = React.useState<HistoryPaperDetailResponse | null>(null);
  const [isLoadingHistoryDetails, setIsLoadingHistoryDetails] = React.useState(false);
  const [isDevicesModalOpen, setIsDevicesModalOpen] = React.useState(false);

  React.useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  const refreshHistorySilently = React.useCallback(() => {
    const tokenToUse = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true' ? "test_token_for_disabled_auth" : user?.token;
    if (!tokenToUse) return;
    fetchUserHistory(tokenToUse)
      .then(data => {
        if (isMountedRef.current && Array.isArray(data)) {
          setExamHistory(data);
        }
      })
      .catch(() => {});
  }, [user?.token]);

  const answeredQuestionsCount = React.useMemo(
    () => answers.filter((a) => a !== null && a !== "-1").length,
    [answers]
  );

  const {
    status: wsStatus,
    deviceId: currentDeviceId,
    devices,
    adminLiveConnections,
    adminLiveEvents,
    joinPaper,
    requestResolveSync,
    leavePaper,
    sendCursorMove,
    syncProgress,
    kickDevice,
    requestAdminLiveState,
    adminKickDevice,
    clearAdminLiveEvents,
  } = useExamWebSocket({
    token: user?.token || (process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true' ? "test_token_for_disabled_auth" : null),
    telemetryContext: {
      pageMode,
      examState,
      paperId: paperData?.paper_id ?? null,
      paperDifficulty: selectedDifficulty || paperData?.difficulty || null,
      currentQuestionIndex,
      answeredCount: answeredQuestionsCount,
      totalQuestions: paperData?.paper?.length ?? 0,
      domPurged: domPurgedByDebugger,
      shieldMasterOn: shieldConfig.master,
      securityAlertCount: shieldEvents.length,
      lastSecurityAlert: shieldEvents[0]?.reason ?? null,
    },
    onAdminPaperUpdated: () => {
      setAdminPaperUpdateVersion((v) => v + 1);
    },
    onPaperState: (evt) => {
      if (paperData && evt.paper_id === paperData.paper_id) {
        if (Array.isArray(evt.selected_uuids)) {
          setAnswers(evt.selected_uuids.map(u => (u && u !== "-1" ? u : null)));
        } else if (Array.isArray(evt.selected_texts)) {
          setAnswers((prev) => mapSelectedTextsToLocalUuids(paperData.paper, evt.selected_texts, prev));
        }
      }
    },
    onResolvedSync: (evt) => {
      if (paperData && evt.paper_id === paperData.paper_id && Array.isArray(evt.selected_uuids)) {
        setAnswers(evt.selected_uuids.map(u => (u && u !== "-1" ? u : null)));
      }
    },
    onProgressSaved: (evt) => {
      if (paperData && evt.paper_id === paperData.paper_id) {
        setAutoSaveStatus('saved');
        setTimeout(() => {
          if (isMountedRef.current) setAutoSaveStatus((prev) => (prev === 'saved' ? 'idle' : prev));
        }, 3000);
      }
    },
    onProgressSynced: (evt) => {
      if (paperData && evt.paper_id === paperData.paper_id) {
        if (paperData.paper_hash) {
          requestResolveSync(paperData.paper_id, paperData.paper_hash);
        } else if (Array.isArray(evt.selected_texts)) {
          setAnswers((prev) => mapSelectedTextsToLocalUuids(paperData.paper, evt.selected_texts, prev));
        }
        setAutoSaveStatus('saved');
        setTimeout(() => {
          if (isMountedRef.current) setAutoSaveStatus((prev) => (prev === 'saved' ? 'idle' : prev));
        }, 3000);
      } else {
        refreshHistorySilently();
      }
    },
    onExamFinished: (evt) => {
      if (paperData && evt.paper_id === paperData.paper_id) {
        const endTime = new Date();
        const durationMs = examStartTime ? endTime.getTime() - examStartTime.getTime() : undefined;
        const resultDisplayData: ResultPageDisplayData = {
          paperId: evt.paper_id,
          durationMs,
          status_code: evt.status_code,
          message: evt.message,
          score: evt.score,
          passcode: evt.passcode,
        };
        setResultData(resultDisplayData);
        setExamState(evt.status_code === 'PASSED' ? 'success' : 'failed');
        setAutoSaveStatus('idle');
      }
      refreshHistorySilently();
    },
    onExamCreated: () => {
      refreshHistorySilently();
    },
    onSyncError: () => {
      if (isMountedRef.current) setAutoSaveStatus('error');
    },
    onKicked: (evt) => {
      toast({ title: t('multiDevice.kickedTitle'), description: evt.reason, variant: 'destructive' });
    },
  });

  const resetExamStateForNewAttempt = React.useCallback(() => {
    leavePaper();
    setPaperData(null); setResultData(null); setExamStartTime(null); setTotalElapsedTime("00:00");
    setCurrentQuestionIndex(0); setAnswers([]); setUnansweredSubmissionSummary(null);
    setAutoSaveStatus('idle'); setPendingInstantStartInfo(null); setConfirmActionInfo(null);
    setSelectedDifficulty(null);
    if (isMountedRef.current) {
      setExamState('selecting_difficulty');
    }
  }, [leavePaper]);

  const handleStartExam = React.useCallback(() => {
    if (paperData && isMountedRef.current) {
      setExamStartTime(new Date());
      setExamState('taking');
      joinPaper(paperData.paper_id, 0, paperData.paper_hash);
    }
  }, [paperData, joinPaper]);

  const fetchExam = React.useCallback(async (difficulty: Difficulty | null, paperIdToResume?: string | null, initialQIndex: number = 0) => {
    const tokenToUse = user?.token || (process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true' ? "test_token_for_disabled_auth" : null);
    if (!tokenToUse && process.env.NEXT_PUBLIC_DISABLE_AUTH !== 'true') {
      if (isMountedRef.current) { setExamState('login_required'); setPageMode('exam_active_direct'); }
      return;
    }
    if (isMountedRef.current) { setExamState('loading'); if (difficulty) setSelectedDifficulty(difficulty); }

    const isResumingViaHistoryOrInput = !!paperIdToResume;
    try {
      let paperForForm: Paper; let initialAnswers: (string | null)[];
      if (isResumingViaHistoryOrInput && paperIdToResume) {
        const historyData: HistoryPaperDetailResponse = await fetchHistoryPaperDetails(tokenToUse!, paperIdToResume);
        if (!historyData || !historyData.paper_id || !Array.isArray(historyData.paper_questions)) {
          if (isMountedRef.current) { setResultData({ message: t('error.fetchExam.invalidData') }); setExamState('error'); } return;
        }
        if (historyData.difficulty && isMountedRef.current) setSelectedDifficulty(historyData.difficulty);

        const issuedQuestions: ExamQuestion[] =
          historyData.paper && historyData.paper.length > 0
            ? historyData.paper
            : historyData.paper_questions.map(q_hist => ({
                body: q_hist.body,
                choices: q_hist.choices || {},
              }));

        paperForForm = {
          paper_id: historyData.paper_id,
          difficulty: historyData.difficulty,
          paper: issuedQuestions,
          paper_hash: historyData.paper_hash,
        };
        initialAnswers = historyData.submitted_answers_card
          ? historyData.submitted_answers_card.map(ans => ans === "-1" ? null : ans)
          : historyData.paper_questions.map(q_hist => q_hist.submitted_answer === "-1" ? null : (q_hist.submitted_answer as string | null));

      } else if (difficulty) {
        const newPaperData = await fetchExamPaper(tokenToUse!, difficulty, null);
        if (!newPaperData || !newPaperData.paper_id || !Array.isArray(newPaperData.paper) || newPaperData.paper.length === 0) {
          if (isMountedRef.current) { setResultData({ message: t('error.fetchExam.invalidData') }); setExamState('error'); } return;
        }
        paperForForm = newPaperData; initialAnswers = Array(paperForForm.paper.length).fill(null);
      } else {
        toast({ title: t('exam_errors.toast.noDifficulty.title'), description: t('exam_errors.toast.noDifficulty.description'), variant: "destructive" });
        if (isMountedRef.current) { setPageMode('user_center'); setExamState('selecting_difficulty'); } return;
      }

      if (isMountedRef.current) {
        const cleanAnswers = initialAnswers.map(ans => (ans === "-1" ? null : ans));
        let targetQIndex = initialQIndex;
        if (isResumingViaHistoryOrInput && initialQIndex === 0) {
          const firstUnansweredIdx = cleanAnswers.findIndex(ans => ans === null);
          if (firstUnansweredIdx >= 0) {
            targetQIndex = firstUnansweredIdx;
          }
        }
        setPaperData(paperForForm);
        setAnswers(cleanAnswers);
        setCurrentQuestionIndex(targetQIndex);
        joinPaper(paperForForm.paper_id, targetQIndex, paperForForm.paper_hash);

        const isThisFetchForInstantStart = pendingInstantStartInfo &&
          ((pendingInstantStartInfo.type === 'difficulty' && difficulty && pendingInstantStartInfo.difficulty === difficulty) ||
           (pendingInstantStartInfo.type === 'resume' && paperIdToResume && pendingInstantStartInfo.paperId === paperIdToResume));

        if (isThisFetchForInstantStart || isResumingViaHistoryOrInput) {
          setExamStartTime(new Date());
          setExamState('taking');
        } else {
          setExamState('welcome');
        }
      }

    } catch (error: any) {
      if (!isMountedRef.current) return;
      let specificErrorMsg = t('error.fetchExam.generic');
      if (String(error.message).includes("401") || String(error.message).includes("Unauthorized") || String(error.message).includes("TOKEN_INVALID") || String(error.status_code).includes("401")) {
        specificErrorMsg = t('auth.toast.sessionExpired.description'); if (refreshToken) await refreshToken(); setExamState('login_required');
      } else if (String(error.message).includes("404") && isResumingViaHistoryOrInput) {
        specificErrorMsg = t('toast.resumeError.notFound'); setPageMode('user_center'); setExamState('selecting_difficulty'); toast({ title: t('toast.resumeError.title'), description: specificErrorMsg, variant: "destructive" }); return;
      } else if (String(error.message).includes("429") || String(error.status_code).includes("429")) {
        setResultData({ message: t('error.fetchExam.rateLimit'), status_code: "429" }); setExamState('rate_limited'); return;
      } else if (error instanceof TypeError && error.message === 'Failed to fetch') specificErrorMsg = t('error.fetchExam.network');
      else if (error instanceof Error && error.message) specificErrorMsg = t('error.fetchExam.apiError', { message: error.message });
      setResultData({ message: specificErrorMsg }); setExamState('error');
    }
  }, [user?.token, t, toast, pendingInstantStartInfo, refreshToken, joinPaper]);

  React.useEffect(() => {
    if (authIsLoading) {
      return;
    }

    const urlDifficultyParam = searchParams.get('d');
    const urlPaperIdParam = searchParams.get('id');
    const urlInstantStartParam = searchParams.get('i') === '1';
    const currentUrlQueryKey = `${urlPaperIdParam || ''}|${urlDifficultyParam || ''}|${urlInstantStartParam ? '1' : '0'}`;

    if (initialUrlParamsProcessedRef.current && lastProcessedUrlQueryRef.current === currentUrlQueryKey) {
      if (pageMode !== 'exam_active_direct' && !confirmActionInfo && !unansweredSubmissionSummary && !resultData && !paperData) {
        if (pageMode !== 'user_center' && pageMode !== 'admin_panel') setPageMode('user_center');
        if (examState !== 'selecting_difficulty' && examState !== 'authenticating') setExamState('selecting_difficulty');
      }
      return;
    }

    let actionTaken = false;

    if (urlPaperIdParam) {
      actionTaken = true;
      setPageMode('exam_active_direct');
      resetExamStateForNewAttempt();
      wasUrlInitiatedRef.current = true;
      shownUrlInitiatedToastRef.current = false;

      if (urlInstantStartParam) {
        setPendingInstantStartInfo({ type: 'resume', paperId: urlPaperIdParam });
        fetchExam(null, urlPaperIdParam);
      } else {
        const displayPaperId = urlPaperIdParam.length > 8 ? `${urlPaperIdParam.substring(0,8)}...` : urlPaperIdParam;
        setConfirmActionInfo({ type: 'resume', paperId: urlPaperIdParam, messageKey: 'urlConfirm.resumeMessage', messageParams: { paperId: displayPaperId }, action: () => { setConfirmActionInfo(null); setPendingInstantStartInfo({ type: 'resume', paperId: urlPaperIdParam }); fetchExam(null, urlPaperIdParam); } });
        setExamState('confirming_url_action');
      }
    } else if (urlDifficultyParam) {
      let mappedDifficulty: Difficulty | null = null;
      if (urlDifficultyParam === 'h') mappedDifficulty = 'hard';
      else if (urlDifficultyParam === 'e') mappedDifficulty = 'easy';
      else if (urlDifficultyParam === 'y') mappedDifficulty = 'hybrid';

      if (mappedDifficulty) {
        actionTaken = true;
        setPageMode('exam_active_direct');
        resetExamStateForNewAttempt();
        wasUrlInitiatedRef.current = true;
        shownUrlInitiatedToastRef.current = false;
        if (urlInstantStartParam) {
          setPendingInstantStartInfo({ type: 'difficulty', difficulty: mappedDifficulty });
          fetchExam(mappedDifficulty, null);
        } else {
          const difficultyLabelKey = `difficulty.${mappedDifficulty}.label` as TranslationKeys;
          setConfirmActionInfo({ type: 'difficulty', difficulty: mappedDifficulty, messageKey: 'urlConfirm.difficultyMessage', messageParams: { difficulty: t(difficultyLabelKey) }, action: () => { setConfirmActionInfo(null); setPendingInstantStartInfo({ type: 'difficulty', difficulty: mappedDifficulty }); fetchExam(mappedDifficulty, null); } });
          setExamState('confirming_url_action');
        }
      }
    }

    if (!actionTaken) {
      if (!initialUrlParamsProcessedRef.current) {
        setPageMode('user_center');
        if (!confirmActionInfo && !unansweredSubmissionSummary && !resultData && !paperData && examState !== 'admin_panel') {
          setExamState('selecting_difficulty');
        }
      }
    }
    initialUrlParamsProcessedRef.current = true;
    lastProcessedUrlQueryRef.current = currentUrlQueryKey;
  }, [searchParams, authIsLoading, resetExamStateForNewAttempt, t, fetchExam, pageMode, confirmActionInfo, unansweredSubmissionSummary, resultData, paperData, examState]);

  React.useEffect(() => {
    if (pendingInstantStartInfo && examState === 'taking' && isMountedRef.current) {
      setPendingInstantStartInfo(null);
    }
  }, [pendingInstantStartInfo, examState]);

  React.useEffect(() => {
    if (paperData?.paper_id && wasUrlInitiatedRef.current && !shownUrlInitiatedToastRef.current && (examState === 'welcome' || examState === 'taking') && isMountedRef.current) {
      toast({ title: t('toast.urlInitiated.title'), description: t('toast.urlInitiated.description', { paperId: paperData.paper_id }), duration: 9000 });
      shownUrlInitiatedToastRef.current = true;
    }
  }, [paperData, examState, t, toast]);

  React.useEffect(() => {
    let isActive = true;
    if (pageMode === 'user_center' && !authIsLoading && isMountedRef.current) {
      const tokenToUse = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true' ? "test_token_for_disabled_auth" : user?.token;

      if (tokenToUse) {
        setIsLoadingHistory(true);
        setHistoryError(null);
        fetchUserHistory(tokenToUse)
          .then(data => {
            if (isActive) {
              setExamHistory(Array.isArray(data) ? data : []);
              if (!Array.isArray(data)) {
                setHistoryError(t('userCenter.history.loadError'));
              }
            }
          })
          .catch(err => {
            if (isActive) {
              setHistoryError(err.message || t('userCenter.history.loadError'));
              setExamHistory([]);
            }
          })
          .finally(() => {
            if (isActive) setIsLoadingHistory(false);
          });
      } else {
        setExamHistory([]);
        setIsLoadingHistory(false);
        setHistoryError(null);
      }
    } else if (pageMode !== 'user_center') {
      if (isActive) setIsLoadingHistory(false);
    }
    return () => { isActive = false; };
  }, [pageMode, user?.token, authIsLoading, t]);

  const sendUpdateToApi = React.useCallback(async (currentPaperObj: Paper, currentAnswers: (string | null)[], qIdx: number) => {
    const tokenToUse = user?.token || (process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true' ? "test_token_for_disabled_auth" : null);
    if (!currentPaperObj?.paper_id || !tokenToUse || !isMountedRef.current) {
      if (isMountedRef.current) setAutoSaveStatus('error');
      setTimeout(() => { if (isMountedRef.current) setAutoSaveStatus(prev => (prev === 'error' ? 'idle' : prev)) }, 3000);
      return;
    }

    if (isMountedRef.current) setAutoSaveStatus('saving');
    const strippedPaper = currentPaperObj.paper.map(q => ({
      body: q.body,
      choices: q.choices,
    }));
    const submissionPayload: Submission = {
      paper_id: currentPaperObj.paper_id,
      paper: strippedPaper,
      paper_hash: currentPaperObj.paper_hash,
      result: currentAnswers.map(ans => ans === null ? "-1" : ans),
      current_question_index: qIdx,
      device_id: currentDeviceId,
    };

    if (wsStatus === 'connected' && syncProgress(submissionPayload)) {
      return;
    }

    try {
      const response: UpdateApiResponse = await updateExamProgress(tokenToUse, submissionPayload);
      if (!isMountedRef.current) return;
      if (response.status_code === "PROGRESS_SAVED") {
        setAutoSaveStatus('saved');
      } else {
        setAutoSaveStatus('error');
        const resStatusCodeStr = String(response.status_code);
        if (resStatusCodeStr.includes("404") || resStatusCodeStr.includes("400") || (response.message && response.message.includes("NOT_FOUND"))) {
          toast({ title: t('toast.updateError.title'), description: t('toast.updateError.paperInvalid'), variant: "destructive" });
          resetExamStateForNewAttempt(); setPageMode('user_center'); setExamState('selecting_difficulty');
        } else if (resStatusCodeStr.includes("401")) {
          toast({ title: t('auth.toast.sessionExpired.title'), description: t('auth.toast.sessionExpired.description'), variant: "destructive" });
          if (refreshToken) await refreshToken(); setExamState('login_required');
        } else {
          toast({ title: t('toast.updateError.title'), description: response.message || t('toast.updateError.generic'), variant: "destructive", duration: 2000 });
        }
      }
    } catch (error) { if (isMountedRef.current) setAutoSaveStatus('error'); }
    finally { setTimeout(() => { if (isMountedRef.current) setAutoSaveStatus(prev => (prev === 'saving' || prev === 'saved' || prev === 'error') ? 'idle' : prev) }, 3000); }
  }, [user?.token, t, toast, resetExamStateForNewAttempt, refreshToken, currentDeviceId, wsStatus, syncProgress]);

  const debouncedSendUpdate = React.useMemo(() => debounce(sendUpdateToApi, 800), [sendUpdateToApi]);

  const handleAnswerChangeAndSave = React.useCallback((qIndex: number, choiceId: string) => {
    const newAnswers = [...answers];
    newAnswers[qIndex] = choiceId;
    setAnswers(newAnswers);

    if (paperData) {
      debouncedSendUpdate(paperData, newAnswers, qIndex);
    }
    if (qIndex < (paperData?.paper?.length || 0) - 1) {
      setCurrentQuestionIndex(qIndex + 1);
      if (paperData?.paper_id) {
        sendCursorMove(paperData.paper_id, qIndex + 1);
      }
    }
  }, [answers, paperData, debouncedSendUpdate, sendCursorMove]);

  const handleQuestionIndexChangeWithWs = React.useCallback((newIdx: number) => {
    setCurrentQuestionIndex(newIdx);
    if (paperData?.paper_id) {
      sendCursorMove(paperData.paper_id, newIdx);
    }
  }, [paperData?.paper_id, sendCursorMove]);

  React.useEffect(() => {
    if ((examState === 'taking' || examState === 'confirming_submission' || examState === 'submitting') && examStartTime) {
      const intervalId = setInterval(() => { if (isMountedRef.current) { const elapsedMs = Date.now() - examStartTime.getTime(); setTotalElapsedTime(formatTimeDisplay(elapsedMs)); } }, 1000);
      return () => clearInterval(intervalId);
    }
  }, [examState, examStartTime]);

  React.useEffect(() => { if (isMountedRef.current) document.title = t('app.title', { brandName: currentBrandName }); }, [t, currentBrandName]);

  const handleDifficultySelectedFromModal = (difficulty: Difficulty) => {
    if (!isMountedRef.current) return;
    setShowDifficultyModal(false);
    wasUrlInitiatedRef.current = false;
    shownUrlInitiatedToastRef.current = false;
    resetExamStateForNewAttempt();
    setSelectedDifficulty(difficulty);
    setPageMode('exam_active_direct');
    fetchExam(difficulty, null);
  };

  const handleRetry = React.useCallback(() => {
    if (!isMountedRef.current) return;
    resetExamStateForNewAttempt();
    setPageMode('user_center');
    setExamState('selecting_difficulty');
    if (searchParams.get('id') || searchParams.get('d')) router.replace('/', { scroll: false });
  }, [resetExamStateForNewAttempt, searchParams, router]);

  const onTriggerSubmitExamForm = React.useCallback(() => {
    if (!paperData || !isMountedRef.current) return;
    const unansweredIndices = answers.reduce((acc, answer, idx) => { if (answer === null) acc.push(idx); return acc; }, [] as number[]);
    const strippedPaper = paperData.paper.map(q => ({
      body: q.body,
      choices: q.choices,
    }));
    const currentSubmission: Submission = {
      paper_id: paperData.paper_id,
      paper: strippedPaper,
      paper_hash: paperData.paper_hash,
      result: answers.map(ans => ans === null ? "-1" : ans),
      device_id: currentDeviceId,
    };
    if (unansweredIndices.length > 0) {
      setUnansweredSubmissionSummary({ indices: unansweredIndices, paperId: currentSubmission.paper_id, submission: currentSubmission });
      setExamState('confirming_submission');
    } else {
      executeSubmitApi(currentSubmission).then(apiResponse => { if (isMountedRef.current) handleApiResult(apiResponse, currentSubmission.paper_id); });
    }
  }, [paperData, answers, currentDeviceId]);

  const handleConfirmSubmitFromSummary = () => {
    if (unansweredSubmissionSummary && isMountedRef.current) {
      executeSubmitApi(unansweredSubmissionSummary.submission).then(apiResponse => {
        if (isMountedRef.current) handleApiResult(apiResponse, unansweredSubmissionSummary.paperId);
      });
      setUnansweredSubmissionSummary(null);
    }
  };
  const handleCancelSubmitFromSummary = () => { if (isMountedRef.current) { setUnansweredSubmissionSummary(null); setExamState('taking'); } };

  const executeSubmitApi = async (submission: Submission): Promise<FinishApiResponse | null> => {
    const tokenToUse = user?.token || (process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true' ? "test_token_for_disabled_auth" : null);
    if ((!tokenToUse && process.env.NEXT_PUBLIC_DISABLE_AUTH !== 'true') || !isMountedRef.current) { if (isMountedRef.current) setExamState('login_required'); return null; }
    if (isMountedRef.current) { setExamState('submitting'); setAutoSaveStatus('idle'); }
    try {
      const resultJson: FinishApiResponse = await finishExamSubmission(tokenToUse!, submission); if (!isMountedRef.current) return null;
      if (String((resultJson as unknown as any).status_code) === "401" || String((resultJson as unknown as any).status_code) === "TOKEN_INVALID" || (resultJson.message && resultJson.message.includes("TOKEN_INVALID"))) {
        toast({ title: t('auth.toast.sessionExpired.title'), description: t('auth.toast.sessionExpired.description'), variant: "destructive" });
        if (refreshToken) await refreshToken();
        setExamState('login_required');
        return null;
      }
      if (resultJson.status_code === "INVALID_SUBMISSION" && !resultJson.message) return { ...resultJson, message: t('error.submit.invalidSubmission') };
      return resultJson;
    } catch (error) { if (!isMountedRef.current) return null; if (error instanceof TypeError && error.message === 'Failed to fetch') return { status_code: 'NETWORK_ERROR', message: t('error.submit.network') }; return { status_code: 'CLIENT_ERROR', message: t('error.submit.generic') }; }
  };

  const handleApiResult = React.useCallback((response: FinishApiResponse | null, paperId: string) => {
    const endTime = new Date(); const durationMs = examStartTime ? endTime.getTime() - examStartTime.getTime() : undefined;
    const resultDisplayData: ResultPageDisplayData = { paperId: paperId, durationMs };
    if (!response) { if (isMountedRef.current && examState !== 'login_required') onResult('error', { ...resultDisplayData, message: t('error.submit.noResponse') }); return; }
    resultDisplayData.status_code = response.status_code; resultDisplayData.message = response.message;
    if ('score' in response && response.score !== undefined) resultDisplayData.score = response.score;
    if ('passcode' in response && response.passcode) resultDisplayData.passcode = response.passcode;
    switch (response.status_code) {
      case "PASSED": onResult('success', resultDisplayData); break;
      case "FAILED": onResult('failed', resultDisplayData); break;
      case "NOT_FOUND": case "ALREADY_GRADED": onResult('error', { ...resultDisplayData, message: response.message || t('error.submit.generic') }); break;
      case "INVALID_SUBMISSION": onResult('error', { ...resultDisplayData, message: response.message || t('error.submit.invalidSubmission') }); break;
      case "429": onResult('rate_limited', { ...resultDisplayData, message: response.message || t('error.submit.rateLimit') }); break;
      default: onResult('error', { ...resultDisplayData, message: resultDisplayData.message || t('error.submit.unknownResponse', { statusCode: String(response.status_code || 'N/A') }) });
    }
    if (response.status_code === "PASSED" || response.status_code === "FAILED" || response.status_code === "NOT_FOUND" || response.status_code === "ALREADY_GRADED") {
      if (isMountedRef.current && user?.uid && process.env.NEXT_PUBLIC_DISABLE_AUTH !== 'true') {
        localStorage.removeItem(`unfinishedPaperId_${user.uid}`);
      } else if (isMountedRef.current && process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true') {
        localStorage.removeItem(`unfinishedPaperId_test_user`);
      }
    }
  }, [examStartTime, examState, t, user?.uid]);

  const onResult = (status: ExamState, data?: ResultPageDisplayData) => { if (!isMountedRef.current) return; setResultData(data || null); setExamState(status); setAutoSaveStatus('idle'); };

  const handleGoBackToUserCenter = React.useCallback(() => {
    if (!isMountedRef.current) return;
    resetExamStateForNewAttempt();
    setPageMode('user_center');
    setExamState('selecting_difficulty');
    if (searchParams.get('id') || searchParams.get('d')) router.replace('/', { scroll: false });
  }, [resetExamStateForNewAttempt, searchParams, router]);

  const handleAdminNavigation = (section: AdminSectionId) => {
    setAdminSelectedSection(section);
    if (section === 'questionBanks') setAdminSelectedDifficultyBank(null);
    if (section === 'home' || section === 'liveMonitor') {
      requestAdminLiveState();
    }
  };
  const handleAdminDifficultyBankNavigation = (difficulty: DifficultyLevel) => {
    setAdminSelectedSection('questionBanks');
    setAdminSelectedDifficultyBank(difficulty);
  };

  React.useEffect(() => {
    if (pageMode === 'admin_panel' && wsStatus === 'connected') {
      requestAdminLiveState();
    }
  }, [pageMode, wsStatus, requestAdminLiveState]);

  const handleContinueExam = React.useCallback((paperId: string) => {
    if (!isMountedRef.current || !paperId) return;
    wasUrlInitiatedRef.current = false;
    shownUrlInitiatedToastRef.current = false;
    resetExamStateForNewAttempt();
    setPageMode('exam_active_direct');
    setPendingInstantStartInfo({ type: 'resume', paperId });
    fetchExam(null, paperId);
  }, [resetExamStateForNewAttempt, fetchExam]);

  const handleViewHistoryDetails = async (paperId: string) => {
    if (!user?.token && process.env.NEXT_PUBLIC_DISABLE_AUTH !== 'true') {
      toast({ title: t('auth.toast.sessionExpired.title'), description: t('auth.toast.sessionExpired.description'), variant: "destructive" });
      return;
    }
    const tokenToUse = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true' ? "test_token_for_disabled_auth" : user!.token;
    setIsLoadingHistoryDetails(true);
    setSelectedHistoryPaperDetails(null);
    setIsHistoryDetailsModalOpen(true);
    try {
      const details = await fetchHistoryPaperDetails(tokenToUse, paperId);
      setSelectedHistoryPaperDetails(details);
    } catch (error: any) {
      toast({
        title: t('userHistory.detailsDialog.fetchErrorTitle'),
        description: error.message || t('userHistory.detailsDialog.fetchErrorDescription', { paperId }),
        variant: 'destructive',
      });
      setIsHistoryDetailsModalOpen(false);
    } finally {
      setIsLoadingHistoryDetails(false);
    }
  };

  React.useEffect(() => {
    if (examState === 'login_required' && isMountedRef.current && process.env.NEXT_PUBLIC_DISABLE_AUTH !== 'true') {
      router.push('/auth/login');
    }
  }, [examState, router]);

  const WelcomeCard = ({ onStart, isLoading }: { onStart: () => void; isLoading: boolean }) => {
    const showSavePrompt = !isLoading && paperData?.paper_id && examState === 'welcome' && !pendingInstantStartInfo && !(wasUrlInitiatedRef.current);
    return (
      <div className="flex min-h-[calc(100vh-3rem)] flex-col items-center justify-center p-4">
        <div className="w-full max-w-md rounded border bg-card">
          <div className="border-b px-5 py-3.5">
            <h2 className="text-base font-semibold text-foreground">
              {t('welcome.title', { brandName: currentBrandName })}
            </h2>
          </div>
          <div className="space-y-3 p-5 text-sm">
            {showSavePrompt && paperData?.paper_id && (
              <div className="rounded border bg-muted/30 p-3 text-xs space-y-1.5">
                <div className="font-medium text-foreground">{t('welcome.saveProgress.title')}</div>
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <span>{t('welcome.saveProgress.messagePart1')}</span>
                  <span className="font-code-extrabold text-foreground">{paperData.paper_id}</span>
                  <CopyButton
                    textToCopy={paperData.paper_id}
                    toastMessageKey="copyButton.toast.success.paperIdCopied"
                    size="sm"
                    className="p-0.5 h-5 w-5"
                    iconClassName="h-3 w-3"
                    title={t('copyButton.copy')}
                  />
                </div>
                <p className="text-muted-foreground">{t('welcome.saveProgress.messagePart2')}</p>
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2 border-t bg-muted/30 px-5 py-3">
            <Button variant="outline" size="sm" onClick={handleGoBackToUserCenter}>
              {t('userCenter.backToHome')}
            </Button>
            <Button onClick={onStart} disabled={isLoading} size="sm">
              {isLoading ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  {t('welcome.button.loading')}
                </>
              ) : (
                t('welcome.button.start')
              )}
            </Button>
          </div>
        </div>
      </div>
    );
  };

  const filteredExamHistory = React.useMemo(() => examHistory.filter(exam => {
    const matchesSearch = !searchTermUser || (exam.paper_id && exam.paper_id.toLowerCase().includes(searchTermUser.toLowerCase()));
    const matchesStatus = statusFilterUser === 'all' || (statusFilterUser === 'IN_PROGRESS' && exam.pass_status === null) || (exam.pass_status && exam.pass_status.toUpperCase() === statusFilterUser);
    const matchesDifficulty = difficultyFilterUser === 'all' || exam.difficulty === difficultyFilterUser;
    return matchesSearch && matchesStatus && matchesDifficulty;
  }), [examHistory, searchTermUser, statusFilterUser, difficultyFilterUser]);

  const userStatusOptions: Array<{value: UserStatusFilter; labelKey: Parameters<typeof t>[0]}> = [
    { value: 'all', labelKey: 'userCenter.filter.status.all' },
    { value: 'PASSED', labelKey: 'userCenter.history.statusPassed' },
    { value: 'FAILED', labelKey: 'userCenter.history.statusFailed' },
    { value: 'IN_PROGRESS', labelKey: 'userCenter.history.statusInProgress' },
  ];
  const userDifficultyOptions: Array<{value: UserDifficultyFilter; labelKey: Parameters<typeof t>[0]}> = [
    { value: 'all', labelKey: 'userCenter.filter.difficulty.all' },
    { value: 'easy', labelKey: 'difficulty.easy.label' },
    { value: 'hybrid', labelKey: 'difficulty.hybrid.label' },
    { value: 'hard', labelKey: 'difficulty.hard.label' },
  ];
  const handleClearUserFilters = () => { setSearchTermUser(''); setStatusFilterUser('all'); setDifficultyFilterUser('all'); };

  const hasAdminPermission = isAdmin || user?.profile?.tags?.some(tag => tag.toUpperCase() === 'ADMIN');

  const renderAdminContent = () => {
    if (!hasAdminPermission) return null;
    switch (adminSelectedSection) {
      case 'home':
        return (
          <AdminHomeView
            user={user}
            onNavigate={handleAdminNavigation}
            wsStatus={wsStatus}
            currentDeviceId={currentDeviceId}
            liveConnections={adminLiveConnections}
            liveEvents={adminLiveEvents}
            onRequestRefreshLive={requestAdminLiveState}
            onKickDevice={adminKickDevice}
            onClearEvents={clearAdminLiveEvents}
            paperUpdateVersion={adminPaperUpdateVersion}
          />
        );
      case 'liveMonitor':
        return (
          <AdminLiveMonitorView
            wsStatus={wsStatus}
            currentDeviceId={currentDeviceId}
            connections={adminLiveConnections}
            events={adminLiveEvents}
            onRequestRefresh={requestAdminLiveState}
            onKickDevice={adminKickDevice}
            onClearEvents={clearAdminLiveEvents}
            onInspectPaper={() => handleAdminNavigation('papers')}
          />
        );
      case 'papers':
        return (
          <AdminPapersView
            user={user}
            liveConnections={adminLiveConnections}
            paperUpdateVersion={adminPaperUpdateVersion}
          />
        );
      case 'questionBanks':
        if (adminSelectedDifficultyBank) return <AdminQuestionBankDifficultyView user={user} difficulty={adminSelectedDifficultyBank} />;
        return <AdminQuestionBanksHomeView onNavigateToDifficulty={handleAdminDifficultyBankNavigation} />;
      case 'users':
        return (
          <AdminUsersView
            user={user}
            liveConnections={adminLiveConnections}
          />
        );
      case 'settings':
        return <AdminSettingsView user={user} />;
      default:
        return (
          <AdminHomeView
            user={user}
            onNavigate={handleAdminNavigation}
            wsStatus={wsStatus}
            currentDeviceId={currentDeviceId}
            liveConnections={adminLiveConnections}
            liveEvents={adminLiveEvents}
            onRequestRefreshLive={requestAdminLiveState}
            onKickDevice={adminKickDevice}
            onClearEvents={clearAdminLiveEvents}
            paperUpdateVersion={adminPaperUpdateVersion}
          />
        );
    }
  };

  const renderContent = () => {
    const isOverlayActive = (['success', 'failed', 'rate_limited', 'error', 'confirming_submission', 'confirming_url_action'].includes(examState) && (resultData !== null || unansweredSubmissionSummary !== null || confirmActionInfo !== null));

    if (authIsLoading) {
      return (
        <div key="auth-loading-screen" className="flex min-h-screen items-center justify-center w-full">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      );
    }

    if (examState === 'confirming_url_action' && confirmActionInfo) {
      return (
        <div key="url-action-confirm-overlay" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 w-full">
          <AlertDialog open={true} onOpenChange={(open) => { if (!open && examState === 'confirming_url_action' && isMountedRef.current) { setConfirmActionInfo(null); resetExamStateForNewAttempt(); setPageMode('user_center'); setExamState('selecting_difficulty'); if (searchParams.get('id') || searchParams.get('d')) router.replace('/', { scroll: false }); } }}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>{t(confirmActionInfo.type === 'resume' ? 'urlConfirm.resumeTitle' : 'urlConfirm.difficultyTitle')}</AlertDialogTitle>
                <AlertDialogDescription>{confirmActionInfo.messageParams ? t(confirmActionInfo.messageKey as TranslationKeys, confirmActionInfo.messageParams) : t(confirmActionInfo.messageKey as TranslationKeys)}</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel onClick={() => { if (isMountedRef.current) { setConfirmActionInfo(null); resetExamStateForNewAttempt(); setPageMode('user_center'); setExamState('selecting_difficulty'); if (searchParams.get('id') || searchParams.get('d')) router.replace('/', { scroll: false }); } }}>{t('urlConfirm.cancelButton')}</AlertDialogCancel>
                <AlertDialogAction onClick={confirmActionInfo.action}>{t('urlConfirm.confirmButton')}</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      );
    }

    if (examState === 'confirming_submission' && unansweredSubmissionSummary) {
      return (
        <div key="confirming-submission-overlay" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 w-full">
          <UnansweredConfirmationCard
            summary={unansweredSubmissionSummary}
            onConfirmSubmit={handleConfirmSubmitFromSummary}
            onCancel={handleCancelSubmitFromSummary}
            onJumpToQuestion={(idx) => { setCurrentQuestionIndex(idx); setUnansweredSubmissionSummary(null); setExamState('taking'); }}
          />
        </div>
      );
    }

    if (['success', 'failed', 'rate_limited', 'error'].includes(examState) && resultData) {
      return (
        <div key="results-overlay" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 w-full">
          <ResultPage status={examState as 'success' | 'failed' | 'rate_limited' | 'error'} data={resultData} onRetry={handleRetry} />
        </div>
      );
    }

    if (pageMode === 'user_center' && !isOverlayActive) {
      return (
        <div className="container mx-auto max-w-5xl px-4 py-6 w-full space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-3">
            <h2 className="text-base font-semibold text-foreground">{t('userCenter.history.title')}</h2>
            <Button
              size="sm"
              onClick={() => { if (isMountedRef.current) setShowDifficultyModal(true); }}
            >
              {t('userCenter.startNewExamButton')}
            </Button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 rounded border bg-card p-3">
            <div className="relative">
              <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                type="search"
                placeholder={t('userCenter.filter.searchPlaceholder')}
                value={searchTermUser}
                onChange={(e) => setSearchTermUser(e.target.value)}
                className="pl-8 h-8 text-xs"
              />
            </div>
            <Select value={statusFilterUser} onValueChange={(value) => setStatusFilterUser(value as UserStatusFilter)}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder={t('userCenter.filter.status.placeholder')} />
              </SelectTrigger>
              <SelectContent>
                {userStatusOptions.map(opt => (
                  <SelectItem key={opt.value} value={opt.value} className="text-xs">{t(opt.labelKey)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={difficultyFilterUser} onValueChange={(value) => setDifficultyFilterUser(value as UserDifficultyFilter)}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder={t('userCenter.filter.difficulty.placeholder')} />
              </SelectTrigger>
              <SelectContent>
                {userDifficultyOptions.map(opt => (
                  <SelectItem key={opt.value} value={opt.value} className="text-xs">{t(opt.labelKey)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={handleClearUserFilters} variant="outline" size="sm" className="h-8 text-xs">
              {t('userCenter.filter.clearButton')}
            </Button>
          </div>

          <div>
            {isLoadingHistory && (
              <div className="flex justify-center py-12 w-full">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            )}
            {historyError && !isLoadingHistory && (
              <div className="rounded border border-destructive/40 bg-destructive/10 p-4 text-xs text-destructive">
                <div className="font-semibold">{t('userCenter.history.loadErrorTitle')}</div>
                <div>{historyError}</div>
              </div>
            )}
            {!isLoadingHistory && !historyError && filteredExamHistory.length === 0 && (
              <div className="rounded border bg-card py-10 text-center text-xs text-muted-foreground">
                {searchTermUser || statusFilterUser !== 'all' || difficultyFilterUser !== 'all'
                  ? t('userCenter.filter.noResults')
                  : t('userCenter.history.noHistory')}
              </div>
            )}
            {!isLoadingHistory && !historyError && filteredExamHistory.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 w-full">
                {filteredExamHistory.map(exam => (
                  <UserCenterExamCard
                    key={exam.paper_id}
                    exam={exam}
                    onViewDetails={() => handleViewHistoryDetails(exam.paper_id)}
                    onContinueExam={handleContinueExam}
                  />
                ))}
              </div>
            )}
          </div>

          <Dialog open={showDifficultyModal} onOpenChange={setShowDifficultyModal}>
            <DialogContent className="sm:max-w-md p-5">
              <DialogHeader className="border-b pb-3">
                <DialogTitle className="text-base font-semibold">{t('difficulty.selection.title')}</DialogTitle>
              </DialogHeader>
              <DifficultySelectionCard onSelectDifficulty={handleDifficultySelectedFromModal} isLoading={examState === 'loading'} />
            </DialogContent>
          </Dialog>
        </div>
      );
    }

    if (pageMode === 'admin_panel' && hasAdminPermission) {
      return (
        <SidebarProvider defaultOpen={adminSidebarOpen} onOpenChange={setAdminSidebarOpen}>
          <div className="flex min-h-screen w-full">
            <AdminSidebar
              currentBrandName={currentBrandName}
              onNavigate={handleAdminNavigation}
              onNavigateToDifficultyBank={handleAdminDifficultyBankNavigation}
              selectedSection={adminSelectedSection}
              selectedDifficultyBank={adminSelectedDifficultyBank}
              liveConnectionCount={adminLiveConnections.length}
            />
            <SidebarInset className="flex flex-col flex-grow w-full">
              <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b bg-card px-4">
                <SidebarTrigger className="md:hidden" />
                <h1 className="text-sm font-semibold">{t('admin.layout.titleShort')}</h1>
                <div className="ml-auto flex items-center gap-1.5">
                  <ThemeToggle />
                  <LanguageToggle />
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs"
                    onClick={() => { setPageMode('user_center'); setAdminSelectedSection('home'); }}
                  >
                    {t('app.nav.toUserView')}
                  </Button>
                </div>
              </header>
              <main className="flex-1 overflow-auto p-4 sm:px-6 w-full">
                {renderAdminContent()}
              </main>
            </SidebarInset>
          </div>
        </SidebarProvider>
      );
    }

    if (pageMode === 'exam_active_direct') {
      switch (examState) {
        case 'loading':
          return <WelcomeCard onStart={handleStartExam} isLoading={true} />;
        case 'welcome':
          return <WelcomeCard onStart={handleStartExam} isLoading={!paperData} />;
        case 'taking':
        case 'submitting':
          if (!paperData) return <WelcomeCard onStart={handleStartExam} isLoading={true} />;
          return (
            <div className="flex flex-col items-center justify-start flex-grow w-full">
              <ExamForm
                paperData={paperData}
                currentQuestionIndex={currentQuestionIndex}
                answers={answers}
                onAnswerChange={handleAnswerChangeAndSave}
                onQuestionIndexChange={handleQuestionIndexChangeWithWs}
                onTriggerSubmit={onTriggerSubmitExamForm}
                isSubmitting={examState === 'submitting'}
                brandName={currentBrandName}
              />
            </div>
          );
        case 'selecting_difficulty':
        case 'authenticating':
          return (
            <div className="flex min-h-[calc(100vh-3rem)] items-center justify-center w-full">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          );
        default:
          return (
            <div className="flex min-h-[calc(100vh-3rem)] items-center justify-center p-4 w-full">
              <div className="w-full max-w-md rounded border bg-card p-5 space-y-3 text-sm">
                <h2 className="font-semibold text-destructive">{t('error.unknownState.title')}</h2>
                <p className="text-muted-foreground text-xs">{t('error.unknownState.description')}</p>
                <div className="flex justify-end pt-2">
                  <Button onClick={handleGoBackToUserCenter} variant="outline" size="sm">
                    {t('userCenter.backToHome')}
                  </Button>
                </div>
              </div>
            </div>
          );
      }
    }

    return (
      <div className="flex min-h-screen items-center justify-center w-full">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  };

  const showUserCenterHeader = pageMode === 'user_center' && user && !authIsLoading;
  const showExamActiveHeader = pageMode === 'exam_active_direct' && (examState === 'taking' || examState === 'confirming_submission' || examState === 'submitting' || (['success', 'failed', 'rate_limited', 'error'].includes(examState) && resultData !== null)) && paperData;

  return (
    <React.Suspense fallback={<div className="flex min-h-screen items-center justify-center w-full"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>}>
      {showUserCenterHeader && (
        <header className="sticky top-0 z-30 flex h-12 items-center justify-between border-b bg-card px-4">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-foreground">{currentBrandName}</span>
            <span className="text-muted-foreground">|</span>
            <span className="font-code-extrabold text-xs text-muted-foreground">{user!.uid}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsDevicesModalOpen(true)}
              title={t('multiDevice.tooltip')}
              className="h-7 gap-1.5 px-2 text-xs"
            >
              <span className={cn("h-2 w-2 rounded-full", wsStatus === 'connected' ? "bg-green-600" : wsStatus === 'connecting' ? "bg-amber-500" : "bg-slate-400")} />
              <span className="hidden sm:inline">{t('multiDevice.tooltip')}</span>
              {devices.length > 0 && <span className="font-code-extrabold">({devices.length})</span>}
            </Button>
            <ThemeToggle />
            <LanguageToggle />
            {hasAdminPermission && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-2.5 text-xs"
                onClick={() => setPageMode('admin_panel')}
              >
                {t('app.nav.toAdminView')}
              </Button>
            )}
            <Link href="/user/profile" passHref>
              <Button variant="ghost" size="sm" className="h-7 px-2 text-xs">
                {t('auth.nav.profile')}
              </Button>
            </Link>
            <Button variant="ghost" size="sm" onClick={logout} className="h-7 px-2 text-xs">
              {t('auth.nav.logout')}
            </Button>
          </div>
        </header>
      )}

      {pageMode === 'exam_active_direct' && showExamActiveHeader && paperData && (
        <ExamInfoBar
          totalElapsedTime={totalElapsedTime}
          paperId={paperData.paper_id}
          difficulty={selectedDifficulty || paperData.difficulty || null}
          autoSaveStatus={autoSaveStatus}
          onGoBackToUserCenter={handleGoBackToUserCenter}
          wsStatus={wsStatus}
          devicesCount={devices.length}
          onOpenDevicesModal={() => setIsDevicesModalOpen(true)}
        />
      )}

      <div className="flex-grow flex flex-col w-full">
        {renderContent()}
      </div>

      <UserHistoryPaperDetailsDialog
        isOpen={isHistoryDetailsModalOpen}
        onOpenChange={setIsHistoryDetailsModalOpen}
        selectedPaperDetails={selectedHistoryPaperDetails}
        isLoadingDetails={isLoadingHistoryDetails}
      />

      <MultiDeviceDialog
        isOpen={isDevicesModalOpen}
        onClose={() => setIsDevicesModalOpen(false)}
        wsStatus={wsStatus}
        currentDeviceId={currentDeviceId}
        devices={devices}
        onKickDevice={kickDevice}
        onJumpToDevicePaper={(paperId, qIdx) => {
          setPageMode('exam_active_direct');
          fetchExam(null, paperId, qIdx);
        }}
      />
    </React.Suspense>
  );
}

export default function HomePage() {
  return (
    <React.Suspense fallback={<div className="flex-grow flex items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>}>
      <ExamPageContent />
    </React.Suspense>
  );
}
