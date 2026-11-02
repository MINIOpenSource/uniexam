"use client";

import React, { useEffect, useState, useMemo, useTransition, useCallback } from 'react';
import { fetchAdminPapers, deleteAdminPaper, fetchAdminPaperDetails as apiFetchAdminPaperDetails } from '@/lib/admin-api';
import type { AdminPaper, PaperDifficulty, PaperFullDetailModel } from '@/types/admin';
import type { ConnectedDevice } from '@/types/exam';
import type { User } from '@/types/auth';
import { AdminPaperCard } from '@/components/admin/AdminPaperCard';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, SearchIcon } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';
import { useToast } from '@/hooks/use-toast';
import { PaperTableDetailsDialogComponent } from '@/components/admin/paper-table';

type StatusFilter = 'all' | 'PASSED' | 'FAILED' | 'UNFINISHED';
type DifficultyFilter = 'all' | PaperDifficulty;
type SortableTimeKey = 'creation_time_utc' | 'submission_time_utc' | 'last_update_time_utc';

type SortConfig = {
  key: SortableTimeKey | null;
  order: 'asc' | 'desc';
};

interface AdminPapersViewProps {
  user: User | null;
  liveConnections?: ConnectedDevice[];
  paperUpdateVersion?: number;
}

export function AdminPapersView({
  user,
  liveConnections = [],
  paperUpdateVersion = 0,
}: AdminPapersViewProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [papers, setPapers] = useState<AdminPaper[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [difficultyFilter, setDifficultyFilter] = useState<DifficultyFilter>('all');
  const [sortConfig, setSortConfig] = useState<SortConfig>({ key: 'creation_time_utc', order: 'desc' });

  const [isDeleting, startDeleteTransition] = useTransition();
  const [isRefreshing, startRefreshTransition] = useTransition();
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [selectedPaperForDialog, setSelectedPaperForDialog] = useState<PaperFullDetailModel | null>(null);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);
  const [paperToDeleteId, setPaperToDeleteId] = useState<string | null>(null);

  const loadPapers = useCallback(async () => {
    if (!user?.token) {
      setError(t('auth.toast.sessionExpired.description'));
      setIsInitialLoading(false);
      return;
    }
    setIsInitialLoading(true);
    try {
      const fetchedPapers = await fetchAdminPapers(user.token);
      if (Array.isArray(fetchedPapers)) {
        setPapers(fetchedPapers);
      }
      setError(null);
    } catch (e: any) {
      setError(e.message || t('admin.papers.error.description'));
    } finally {
      setIsInitialLoading(false);
    }
  }, [user?.token, t]);

  useEffect(() => {
    if (user?.token) {
      loadPapers();
    } else if (user === null) {
      setError(t('auth.toast.sessionExpired.description'));
      setIsInitialLoading(false);
    }
  }, [user, loadPapers, t]);

  // Silent real-time update whenever WebSocket reports a paper created/updated/finished
  useEffect(() => {
    if (!user?.token || paperUpdateVersion === 0) return;
    fetchAdminPapers(user.token)
      .then((fetched) => {
        if (Array.isArray(fetched)) {
          setPapers(fetched);
        }
      })
      .catch(() => {});
  }, [user?.token, paperUpdateVersion]);

  const liveDeviceByPaperId = useMemo(() => {
    const map = new Map<string, ConnectedDevice>();
    for (const conn of liveConnections) {
      if (conn.active_paper_id) {
        map.set(conn.active_paper_id, conn);
      }
    }
    return map;
  }, [liveConnections]);

  const refreshPapers = async () => {
    if (!user?.token) {
      toast({ title: t('admin.papers.toast.refreshError.title'), description: t('auth.toast.sessionExpired.description'), variant: 'destructive' });
      return;
    }
    try {
      const fetchedPapers = await fetchAdminPapers(user.token);
      if (Array.isArray(fetchedPapers)) {
        setPapers(fetchedPapers);
      }
      setError(null);
      toast({ title: t('admin.papers.toast.refreshed.title'), description: t('admin.papers.toast.refreshed.description') });
    } catch (e: any) {
      setError(e.message || t('admin.papers.error.description'));
      toast({ title: t('admin.papers.toast.refreshError.title'), description: e.message || t('admin.papers.error.description'), variant: 'destructive' });
    }
  };

  const handleRefreshClick = () => {
    startRefreshTransition(async () => {
      await refreshPapers();
    });
  };

  const filteredAndSortedPapers = useMemo(() => {
    const tempPapers = papers.filter(paper => {
      const matchesSearchTerm = !searchTerm ||
        (paper.paper_id && paper.paper_id.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (paper.user_uid && paper.user_uid.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (paper.passcode && paper.passcode.toLowerCase().includes(searchTerm.toLowerCase()));
      const matchesStatus = statusFilter === 'all' ||
        (statusFilter === 'UNFINISHED' && paper.pass_status === null) ||
        (paper.pass_status && paper.pass_status.toUpperCase() === statusFilter);
      const matchesDifficulty = difficultyFilter === 'all' || paper.difficulty === difficultyFilter;
      return matchesSearchTerm && matchesStatus && matchesDifficulty;
    });

    if (sortConfig.key) {
      tempPapers.sort((a, b) => {
        const valA = a[sortConfig.key!];
        const valB = b[sortConfig.key!];
        if (!valA && !valB) return 0;
        if (valA === null || valA === undefined) return sortConfig.order === 'asc' ? -1 : 1;
        if (valB === null || valB === undefined) return sortConfig.order === 'asc' ? 1 : -1;
        const dateA = new Date(valA).getTime();
        const dateB = new Date(valB).getTime();
        if (isNaN(dateA) && isNaN(dateB)) return 0;
        if (isNaN(dateA)) return sortConfig.order === 'asc' ? -1 : 1;
        if (isNaN(dateB)) return sortConfig.order === 'asc' ? 1 : -1;
        if (dateA < dateB) return sortConfig.order === 'asc' ? -1 : 1;
        if (dateA > dateB) return sortConfig.order === 'asc' ? 1 : -1;
        return 0;
      });
    }
    return tempPapers;
  }, [papers, searchTerm, statusFilter, difficultyFilter, sortConfig]);

  const handleDeletePaper = async (paperId: string) => {
    if (!user?.token) {
      toast({ title: t('admin.papers.toast.deleteError.title'), description: t('auth.toast.sessionExpired.description'), variant: 'destructive' });
      return;
    }
    startDeleteTransition(async () => {
      try {
        await deleteAdminPaper(user.token, paperId);
        setPapers((prevPapers) => prevPapers.filter((p) => p.paper_id !== paperId));
        toast({ title: t('admin.papers.toast.deleted.title'), description: t('admin.papers.toast.deleted.description', { paperId }) });
      } catch (error: any) {
        toast({
          title: t('admin.papers.toast.deleteError.title'),
          description: error.message || t('admin.papers.toast.deleteError.description', { paperId }),
          variant: 'destructive',
        });
      } finally {
        setPaperToDeleteId(null);
      }
    });
  };

  const openDeleteConfirmation = (paperId: string) => {
    setPaperToDeleteId(paperId);
  };

  const handleViewDetails = async (paperSummary: AdminPaper) => {
    if (!user?.token) {
      toast({ title: t('admin.papers.toast.fetchDetailsError.title'), description: t('auth.toast.sessionExpired.description'), variant: 'destructive' });
      setIsDetailsModalOpen(false);
      return;
    }
    setSelectedPaperForDialog(null);
    setIsDetailsModalOpen(true);
    setIsLoadingDetails(true);
    try {
      const details: PaperFullDetailModel = await apiFetchAdminPaperDetails(user.token, paperSummary.paper_id);
      setSelectedPaperForDialog(details);
    } catch (error: any) {
      toast({
        title: t('admin.papers.toast.fetchDetailsError.title'),
        description: error.message || t('admin.papers.toast.fetchDetailsError.description', { paperId: paperSummary.paper_id }),
        variant: 'destructive',
      });
      setIsDetailsModalOpen(false);
    } finally {
      setIsLoadingDetails(false);
    }
  };

  const handleClearFilters = () => {
    setSearchTerm('');
    setStatusFilter('all');
    setDifficultyFilter('all');
    setSortConfig({ key: 'creation_time_utc', order: 'desc' });
  };

  const statusOptions: Array<{value: StatusFilter; labelKey: Parameters<typeof t>[0]}> = [
    { value: 'all', labelKey: 'admin.papers.filter.status.all' },
    { value: 'PASSED', labelKey: 'admin.papers.filter.status.passed' },
    { value: 'FAILED', labelKey: 'admin.papers.filter.status.failed' },
    { value: 'UNFINISHED', labelKey: 'admin.papers.filter.status.unfinished' },
  ];

  const difficultyOptions: Array<{value: DifficultyFilter; labelKey: Parameters<typeof t>[0]}> = [
    { value: 'all', labelKey: 'admin.papers.filter.difficulty.all' },
    { value: 'easy', labelKey: 'difficulty.easy.label' },
    { value: 'hybrid', labelKey: 'difficulty.hybrid.label' },
    { value: 'hard', labelKey: 'difficulty.hard.label' },
  ];

  const sortKeyOptions: Array<{value: SortableTimeKey; labelKey: Parameters<typeof t>[0]}> = [
    { value: 'creation_time_utc', labelKey: 'admin.papers.sort.creationTime' },
    { value: 'submission_time_utc', labelKey: 'admin.papers.sort.submissionTime' },
    { value: 'last_update_time_utc', labelKey: 'admin.papers.sort.lastUpdateTime' },
  ];

  const sortOrderOptions: Array<{value: 'asc' | 'desc'; labelKey: Parameters<typeof t>[0]}> = [
    { value: 'asc', labelKey: 'admin.papers.sort.ascending' },
    { value: 'desc', labelKey: 'admin.papers.sort.descending' },
  ];

  if (isInitialLoading && !user?.token) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mr-2" />
        <span className="text-xs text-muted-foreground">{t('admin.papers.table.loading')}</span>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-3">
          <h2 className="text-base font-semibold text-foreground">{t('admin.papers.title')}</h2>
          <Button
            onClick={handleRefreshClick}
            variant="outline"
            size="sm"
            disabled={isInitialLoading || isRefreshing || !user?.token}
            className="h-8 text-xs"
          >
            {isRefreshing && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {t('admin.papers.refreshButton')}
          </Button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-2.5 rounded border bg-card p-3">
          <div className="relative lg:col-span-2">
            <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              type="search"
              placeholder={t('admin.papers.search.placeholder')}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-8 h-8 text-xs"
            />
          </div>
          <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as StatusFilter)}>
            <SelectTrigger className="h-8 text-xs"><SelectValue placeholder={t('admin.papers.filter.status.placeholder')} /></SelectTrigger>
            <SelectContent>
              {statusOptions.map(opt => (<SelectItem key={opt.value} value={opt.value} className="text-xs">{t(opt.labelKey)}</SelectItem>))}
            </SelectContent>
          </Select>
          <Select value={difficultyFilter} onValueChange={(value) => setDifficultyFilter(value as DifficultyFilter)}>
            <SelectTrigger className="h-8 text-xs"><SelectValue placeholder={t('admin.papers.filter.difficulty.placeholder')} /></SelectTrigger>
            <SelectContent>
              {difficultyOptions.map(opt => (<SelectItem key={opt.value} value={opt.value} className="text-xs">{t(opt.labelKey)}</SelectItem>))}
            </SelectContent>
          </Select>
          <Select value={sortConfig.key || ''} onValueChange={(value) => setSortConfig(prev => ({ ...prev, key: value as SortableTimeKey | null}))}>
            <SelectTrigger className="h-8 text-xs"><SelectValue placeholder={t('admin.papers.sort.placeholderKey')} /></SelectTrigger>
            <SelectContent>
              {sortKeyOptions.map(opt => (<SelectItem key={opt.value} value={opt.value} className="text-xs">{t(opt.labelKey)}</SelectItem>))}
            </SelectContent>
          </Select>
          <div className="flex gap-1.5">
            <Select value={sortConfig.order} onValueChange={(value) => setSortConfig(prev => ({ ...prev, order: value as 'asc' | 'desc' }))} disabled={!sortConfig.key}>
              <SelectTrigger className="h-8 text-xs flex-1"><SelectValue placeholder={t('admin.papers.sort.placeholderOrder')} /></SelectTrigger>
              <SelectContent>
                {sortOrderOptions.map(opt => (<SelectItem key={opt.value} value={opt.value} className="text-xs">{t(opt.labelKey)}</SelectItem>))}
              </SelectContent>
            </Select>
            <Button onClick={handleClearFilters} variant="outline" size="sm" className="h-8 px-2.5 text-xs shrink-0">
              {t('admin.papers.filter.clearButton')}
            </Button>
          </div>
        </div>

        <div>
          {isInitialLoading && user?.token ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mr-2" />
              <span className="text-xs text-muted-foreground">{t('admin.papers.table.loading')}</span>
            </div>
          ) : error ? (
            <div className="rounded border border-destructive/40 bg-destructive/10 p-4 text-xs text-destructive">
              <div className="font-semibold">{t('admin.papers.error.title')}</div>
              <div>{error}</div>
            </div>
          ) : filteredAndSortedPapers.length === 0 ? (
            <div className="rounded border bg-card py-10 text-center text-xs text-muted-foreground">
              {searchTerm || statusFilter !== 'all' || difficultyFilter !== 'all' || (sortConfig.key && sortConfig.key !== 'creation_time_utc')
                ? t('admin.papers.search.noResults')
                : t('admin.papers.table.noPapers')}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {filteredAndSortedPapers.map(paper => (
                <AdminPaperCard
                  key={paper.paper_id}
                  paper={paper}
                  liveDevice={liveDeviceByPaperId.get(paper.paper_id) || null}
                  onViewDetails={() => handleViewDetails(paper)}
                  onDelete={() => openDeleteConfirmation(paper.paper_id)}
                  isDeleting={isDeleting && paperToDeleteId === paper.paper_id}
                  isViewingDetails={isLoadingDetails && selectedPaperForDialog?.paper_id === paper.paper_id}
                  selectedPaperIdForAction={isDeleting ? paperToDeleteId : (isLoadingDetails && selectedPaperForDialog ? selectedPaperForDialog.paper_id : null)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {paperToDeleteId && (
        <AlertDialog open={!!paperToDeleteId} onOpenChange={() => setPaperToDeleteId(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('admin.papers.table.deleteDialog.title')}</AlertDialogTitle>
              <AlertDialogDescription>
                {t('admin.papers.table.deleteDialog.description', { paperId: paperToDeleteId })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isDeleting} onClick={() => setPaperToDeleteId(null)}>{t('admin.papers.table.deleteDialog.cancel')}</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => handleDeletePaper(paperToDeleteId)}
                disabled={isDeleting}
                className="bg-destructive hover:bg-destructive/90"
              >
                {isDeleting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> {t('admin.papers.table.deleteDialog.deleting')}</> : t('admin.papers.table.deleteDialog.delete')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}

      <PaperTableDetailsDialogComponent
        isOpen={isDetailsModalOpen}
        onOpenChange={setIsDetailsModalOpen}
        selectedPaperDetails={selectedPaperForDialog}
        isLoadingDetails={isLoadingDetails}
      />
    </>
  );
}
