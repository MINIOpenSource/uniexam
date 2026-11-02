
"use client";
import React, { useEffect, useState, useMemo, useTransition, useCallback } from 'react';
import { fetchAdminPapers, deleteAdminPaper, fetchAdminPaperDetails as apiFetchAdminPaperDetails } from '@/lib/admin-api';
import type { AdminPaper, PaperDifficulty, PaperFullDetailModel } from '@/types/admin';
import { AdminPaperCard } from '@/components/admin/AdminPaperCard';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
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
import { Label } from '@/components/ui/label';
import { AlertTriangle, Loader2, SearchIcon, FilterXIcon, RefreshCwIcon, ArrowUp, ArrowDown } from 'lucide-react';
import { useTranslation } from '@/hooks/useTranslation';
import { useToast } from '@/hooks/use-toast';
import { PaperTableDetailsDialogComponent } from '@/components/admin/paper-table';
import { useAuth } from '@/context/AuthContext';

type StatusFilter = 'all' | 'PASSED' | 'FAILED' | 'UNFINISHED' | 'PENDING_REVIEW'; // Added PENDING_REVIEW
type DifficultyFilter = 'all' | PaperDifficulty;
type SortableTimeKey = 'creation_time_utc' | 'submission_time_utc' | 'last_update_time_utc';

type SortConfig = {
  key: SortableTimeKey | null;
  order: 'asc' | 'desc';
};

export default function AdminPapersPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { user, isLoading: authIsLoading } = useAuth();

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

  useEffect(() => {
    let isActive = true;

    const loadInitialData = async () => {
      if (!user?.token) {
        if (isActive) {
          setError(t('auth.toast.sessionExpired.description'));
          setPapers([]); // Clear papers if no token
          setIsInitialLoading(false);
        }
        return;
      }
      
      // Only set loading true if not already loading (avoids flicker on token refresh)
      if (isActive && !isInitialLoading) {
        setIsInitialLoading(true);
      }
      setError(null); // Clear previous errors

      try {
        // API v3: fetchAdminPapers uses GET /admin/papers
        const fetchedPapers: AdminPaper[] = await fetchAdminPapers(user.token) as AdminPaper[]; // Cast if Blob is not expected here
        if (isActive) {
          setPapers(fetchedPapers);
        }
      } catch (e: any) {
        if (isActive) {
          console.error("Failed to load papers:", e);
          setError(e.message || t('admin.papers.error.description'));
        }
      } finally {
        if (isActive) {
          setIsInitialLoading(false);
        }
      }
    };

    if (authIsLoading) {
      // If auth is loading, ensure we show the initial loader and don't fetch.
      // This handles the case where the effect runs before auth is resolved.
      if (isActive && !isInitialLoading) setIsInitialLoading(true);
      return; 
    }

    // Auth is resolved at this point
    if (user?.token) {
      loadInitialData();
    } else {
      // Auth resolved, but no user/token
      if (isActive) {
        setError(t('auth.toast.sessionExpired.description'));
        setPapers([]);
        setIsInitialLoading(false);
      }
    }

    return () => {
      isActive = false;
    };
  // Removed isInitialLoading from dependencies. Added authIsLoading
  }, [user?.token, authIsLoading, t]); 

  const refreshData = useCallback(async () => {
    if (!user?.token) {
      toast({ title: t('admin.papers.toast.refreshError.title'), description: t('auth.toast.sessionExpired.description'), variant: 'destructive' });
      return;
    }
    try {
      const fetchedPapers: AdminPaper[] = await fetchAdminPapers(user.token) as AdminPaper[];
      setPapers(fetchedPapers);
      setError(null);
      toast({ title: t('admin.papers.toast.refreshed.title'), description: t('admin.papers.toast.refreshed.description') });
    } catch (e: any) {
      console.error("Failed to refresh papers:", e);
      toast({ title: t('admin.papers.toast.refreshError.title'), description: e.message || t('admin.papers.error.description'), variant: 'destructive' });
    }
  }, [user?.token, t, toast]);

  const handleRefreshClick = () => {
    startRefreshTransition(async () => {
      await refreshData();
    });
  };

  const filteredAndSortedPapers = useMemo(() => {
    let tempPapers = papers.filter(paper => {
      const matchesSearchTerm = !searchTerm ||
        (paper.paper_id && paper.paper_id.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (paper.passcode && paper.passcode.toLowerCase().includes(searchTerm.toLowerCase()));

      const matchesStatus = statusFilter === 'all' ||
        (statusFilter === 'UNFINISHED' && paper.pass_status === null) || // Still relevant for papers not yet submitted/finished
        (statusFilter === 'PENDING_REVIEW' && paper.pass_status?.toUpperCase() === 'PENDING_REVIEW') ||
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
        // API v3: deleteAdminPaper uses DELETE /admin/papers/{paper_id}
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
      // API v3: apiFetchAdminPaperDetails uses GET /admin/papers/{paper_id}
      const details = await apiFetchAdminPaperDetails(user.token, paperSummary.paper_id);
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
    { value: 'PENDING_REVIEW', labelKey: 'admin.papers.filter.status.pendingReview' }, // New
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

  const sortOrderOptions: Array<{value: 'asc' | 'desc'; labelKey: Parameters<typeof t>[0]; icon: React.ElementType}> = [
    { value: 'asc', labelKey: 'admin.papers.sort.ascending', icon: ArrowUp },
    { value: 'desc', labelKey: 'admin.papers.sort.descending', icon: ArrowDown },
  ];

  if (authIsLoading && isInitialLoading) { // Show loader if auth is pending AND initial data load hasn't completed
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center w-full">
        <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">{t('admin.papers.table.loading')}</p>
      </div>
    );
  }


  return (
    <>
      <Card className="shadow-lg animate-in fade-in-0 duration-500 w-full">
        <CardHeader>
          <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-2">
            <div>
              <CardTitle>{t('admin.papers.title')}</CardTitle>
              <CardDescription>{t('admin.papers.description')}</CardDescription>
            </div>
            <Button
              onClick={handleRefreshClick}
              variant="outline"
              size="sm"
              disabled={isInitialLoading || isRefreshing || !user?.token}
              className="w-full sm:w-auto"
            >
              {isRefreshing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCwIcon className="mr-2 h-4 w-4" />}
              {t('admin.papers.refreshButton')}
            </Button>
          </div>
          <div className="mt-4 space-y-4">
            <div className="relative">
              <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type="search"
                placeholder={t('admin.papers.search.placeholder')}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 w-full sm:w-2/3 md:w-1/2"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 items-end">
              <div>
                <Label htmlFor="status-filter">{t('admin.papers.filter.status.label')}</Label>
                <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as StatusFilter)}>
                  <SelectTrigger id="status-filter">
                    <SelectValue placeholder={t('admin.papers.filter.status.placeholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    {statusOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>{t(opt.labelKey)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="difficulty-filter">{t('admin.papers.filter.difficulty.label')}</Label>
                <Select value={difficultyFilter} onValueChange={(value) => setDifficultyFilter(value as DifficultyFilter)}>
                  <SelectTrigger id="difficulty-filter">
                    <SelectValue placeholder={t('admin.papers.filter.difficulty.placeholder')} />
                  </SelectTrigger>
                  <SelectContent>
                     {difficultyOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>{t(opt.labelKey)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="sort-key-filter">{t('admin.papers.sort.label')}</Label>
                <Select
                  value={sortConfig.key || ''}
                  onValueChange={(value) => setSortConfig(prev => ({ ...prev, key: value as SortableTimeKey }))}
                >
                  <SelectTrigger id="sort-key-filter">
                    <SelectValue placeholder={t('admin.papers.sort.placeholderKey')} />
                  </SelectTrigger>
                  <SelectContent>
                    {sortKeyOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>{t(opt.labelKey)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="sort-order-filter">{t('admin.papers.sort.orderLabel')}</Label>
                 <Select
                    value={sortConfig.order}
                    onValueChange={(value) => setSortConfig(prev => ({ ...prev, order: value as 'asc' | 'desc' }))}
                    disabled={!sortConfig.key}
                  >
                    <SelectTrigger id="sort-order-filter">
                      <SelectValue placeholder={t('admin.papers.sort.placeholderOrder')} />
                    </SelectTrigger>
                    <SelectContent>
                      {sortOrderOptions.map(opt => (
                        <SelectItem key={opt.value} value={opt.value}>
                          <div className="flex items-center">
                            <opt.icon className="mr-2 h-4 w-4" />
                            {t(opt.labelKey)}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
              </div>
              <Button onClick={handleClearFilters} variant="outline" className="w-full sm:w-auto md:self-end">
                <FilterXIcon className="mr-2 h-4 w-4" />
                {t('admin.papers.filter.clearButton')}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-4 md:p-6 w-full">
          {isInitialLoading && papers.length === 0 ? ( // More specific condition for initial loader for papers
            <div className="flex flex-col items-center justify-center py-20 text-center w-full">
              <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
              <p className="text-muted-foreground">{t('admin.papers.table.loading')}</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center text-center text-destructive p-6 bg-destructive/10 rounded-md w-full">
              <AlertTriangle className="h-10 w-10 mb-3" />
              <p className="font-semibold mb-1">{t('admin.papers.error.title')}</p>
              <p className="text-sm">{error}</p>
            </div>
          ) : filteredAndSortedPapers.length === 0 ? (
            <div className="text-center py-10 w-full">
              <p className="text-muted-foreground">
                {searchTerm || statusFilter !== 'all' || difficultyFilter !== 'all' || (sortConfig.key && sortConfig.key !== 'creation_time_utc') ? t('admin.papers.search.noResults') : t('admin.papers.table.noPapers')}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 md:gap-6 w-full">
              {filteredAndSortedPapers.map(paper => (
                <AdminPaperCard
                  key={paper.paper_id}
                  paper={paper}
                  onViewDetails={() => handleViewDetails(paper)}
                  onDelete={() => openDeleteConfirmation(paper.paper_id)}
                  isDeleting={isDeleting && paperToDeleteId === paper.paper_id}
                  isViewingDetails={isLoadingDetails && selectedPaperForDialog?.paper_id === paper.paper_id}
                  selectedPaperIdForAction={isDeleting ? paperToDeleteId : (isLoadingDetails && selectedPaperForDialog ? selectedPaperForDialog.paper_id : null)}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

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
