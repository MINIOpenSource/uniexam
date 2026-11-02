"use client";
import React, { useState, useEffect, useCallback } from 'react';
import type { User } from '@/types/auth';
import type { SettingsResponseModel, SettingsUpdatePayload } from '@/types/admin';
import { useSettings } from '@/context/SettingsContext';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from '@/hooks/useTranslation';
import { Loader2 } from 'lucide-react';
import { fetchAdminSettings, updateAdminSettings } from '@/lib/admin-api';

interface AdminSettingsViewProps {
  user: User | null;
}

export function AdminSettingsView({ user }: AdminSettingsViewProps) {
  const { settings: localSettings, setSetting: setLocalSetting, isLoadingSettings: localSettingsLoading } = useSettings();
  const { t } = useTranslation();
  const { toast } = useToast();

  const [currentBrandName, setCurrentBrandName] = useState('');
  const [isFetchingRemoteSettings, setIsFetchingRemoteSettings] = useState(true);
  const [isSavingRemoteSettings, setIsSavingRemoteSettings] = useState(false);
  const [remoteSettingsError, setRemoteSettingsError] = useState<string | null>(null);

  const loadRemoteSettings = useCallback(async () => {
    if (!user?.token) {
      setIsFetchingRemoteSettings(false);
      if (!localSettingsLoading) {
        setCurrentBrandName(localSettings.brandName || '');
      }
      return;
    }
    setIsFetchingRemoteSettings(true);
    setRemoteSettingsError(null);
    try {
      const remoteData: SettingsResponseModel = await fetchAdminSettings(user.token);
      setCurrentBrandName(remoteData.app_name || localSettings.brandName || '');
    } catch (error: any) {
      setRemoteSettingsError(t('admin.settings.toast.fetchError.description', { message: error.message }));
      toast({ title: t('admin.settings.toast.fetchError.title'), description: error.message, variant: 'destructive' });
      if (!localSettingsLoading) {
        setCurrentBrandName(localSettings.brandName || '');
      }
    } finally {
      setIsFetchingRemoteSettings(false);
    }
  }, [user?.token, t, localSettings.brandName, localSettingsLoading, toast]);

  useEffect(() => {
    loadRemoteSettings();
  }, [loadRemoteSettings]);

  const handleSaveSettings = async () => {
    if (!user?.token) {
      toast({ title: t('admin.settings.toast.saveError.title'), description: t('auth.toast.sessionExpired.description'), variant: 'destructive' });
      return;
    }
    setIsSavingRemoteSettings(true);
    setRemoteSettingsError(null);

    const payload: SettingsUpdatePayload = { app_name: currentBrandName };

    try {
      await updateAdminSettings(user.token, payload);
      setLocalSetting('brandName', currentBrandName);
      toast({ title: t('admin.settings.toast.success.title'), description: t('admin.settings.toast.success.description') });
    } catch (error: any) {
      setRemoteSettingsError(t('admin.settings.toast.saveError.description', { message: error.message }));
      toast({ title: t('admin.settings.toast.saveError.title'), description: error.message, variant: 'destructive' });
    } finally {
      setIsSavingRemoteSettings(false);
    }
  };

  if (isFetchingRemoteSettings || localSettingsLoading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (remoteSettingsError && !currentBrandName) {
    return (
      <div className="rounded border border-destructive/40 bg-destructive/10 p-4 text-xs text-destructive">
        <div className="font-semibold">{t('admin.settings.toast.fetchError.title')}</div>
        <div>{remoteSettingsError}</div>
      </div>
    );
  }

  return (
    <div className="max-w-xl rounded border bg-card">
      <div className="border-b px-4 py-3">
        <h2 className="text-sm font-semibold text-foreground">{t('admin.settings.title')}</h2>
      </div>
      <div className="p-4 space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="brandName" className="text-xs">{t('admin.settings.brandName.label')}</Label>
          <Input
            id="brandName"
            value={currentBrandName}
            onChange={(e) => setCurrentBrandName(e.target.value)}
            placeholder={t('admin.settings.brandName.placeholder')}
            className="h-9 text-sm"
          />
        </div>
      </div>
      <div className="flex justify-end border-t bg-muted/30 px-4 py-3">
        <Button size="sm" onClick={handleSaveSettings} disabled={isSavingRemoteSettings || !user?.token}>
          {isSavingRemoteSettings && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
          {t('admin.settings.saveButton')}
        </Button>
      </div>
    </div>
  );
}
