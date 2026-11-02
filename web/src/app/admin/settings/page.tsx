
"use client"; 

import React, { useState, useEffect, useCallback } from 'react';
import { useSettings } from '@/context/SettingsContext';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from '@/hooks/useTranslation';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { fetchAdminSettings, updateAdminSettings } from '@/lib/admin-api';
import type { SettingsResponseModel, SettingsUpdatePayload } from '@/types/admin';

export default function AdminSettingsPage() {
  const { settings: localSettings, setSetting: setLocalSetting, isLoadingSettings: localSettingsLoading } = useSettings();
  const { t } = useTranslation();
  const { toast } = useToast();
  const { user, isLoading: authIsLoading } = useAuth();

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
    if (!authIsLoading) { // Only attempt to load settings once auth state is resolved
      loadRemoteSettings();
    }
  }, [authIsLoading, loadRemoteSettings]);


  const handleSaveSettings = async () => {
    if (!user?.token) {
      toast({ title: t('admin.settings.toast.saveError.title'), description: t('auth.toast.sessionExpired.description'), variant: 'destructive' });
      return;
    }
    setIsSavingRemoteSettings(true);
    setRemoteSettingsError(null);

    const payload: SettingsUpdatePayload = {
      app_name: currentBrandName,
    };

    try {
      await updateAdminSettings(user.token, payload);
      setLocalSetting('brandName', currentBrandName); 
      toast({
        title: t('admin.settings.toast.success.title'),
        description: t('admin.settings.toast.success.description'),
      });
    } catch (error: any) {
       setRemoteSettingsError(t('admin.settings.toast.saveError.description', { message: error.message }));
      toast({ title: t('admin.settings.toast.saveError.title'), description: error.message, variant: 'destructive' });
    } finally {
      setIsSavingRemoteSettings(false);
    }
  };

  if (authIsLoading || isFetchingRemoteSettings || localSettingsLoading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (remoteSettingsError && !currentBrandName && !user?.token) { // Show error only if fetch failed AND user is not authenticated (meaning local fallback also isn't desirable)
    return (
      <Card className="shadow-lg">
        <CardHeader>
          <CardTitle className="text-destructive">{t('admin.settings.toast.fetchError.title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p>{remoteSettingsError}</p>
          {!user?.token && <p className="mt-2 text-sm text-muted-foreground">{t('auth.toast.sessionExpired.description')}</p>}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-lg">
        <CardHeader>
          <CardTitle>{t('admin.settings.title')}</CardTitle>
          <CardDescription>{t('admin.settings.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="brandName">{t('admin.settings.brandName.label')}</Label>
            <Input
              id="brandName"
              value={currentBrandName}
              onChange={(e) => setCurrentBrandName(e.target.value)}
              placeholder={t('admin.settings.brandName.placeholder')}
            />
            <p className="text-xs text-muted-foreground">
              {t('admin.settings.brandName.hint')}
            </p>
          </div>
        </CardContent>
        <CardFooter>
          <Button onClick={handleSaveSettings} disabled={isSavingRemoteSettings || !user?.token}>
            {isSavingRemoteSettings && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('admin.settings.saveButton')}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}

