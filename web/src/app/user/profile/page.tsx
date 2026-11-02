"use client";

import * as React from 'react';
import { ProfileUpdateForm } from '@/components/user/ProfileUpdateForm';
import { PasswordChangeForm } from '@/components/user/PasswordChangeForm';
import { ProtectedRoute, useAuth } from '@/context/AuthContext';
import { useTranslation } from '@/hooks/useTranslation';
import { Loader2 } from 'lucide-react';

function UserProfilePageContent() {
  const { user, isLoading: authLoading } = useAuth();
  const { t } = useTranslation();

  if (authLoading || !user) {
    return (
      <div className="flex min-h-[calc(100vh-3rem)] items-center justify-center p-4">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-2xl py-6 px-4 space-y-6">
      <div className="flex items-center justify-between border-b pb-3">
        <h1 className="text-lg font-semibold">{t('userProfile.pageTitle')}</h1>
        <span className="font-code-extrabold text-xs text-muted-foreground">UID: {user.uid}</span>
      </div>

      <div className="rounded border bg-card">
        <div className="border-b bg-muted/30 px-4 py-2.5">
          <h2 className="text-sm font-medium">{t('userProfile.updateForm.title')}</h2>
        </div>
        <div className="p-4">
          <ProfileUpdateForm />
        </div>
      </div>

      <div className="rounded border bg-card">
        <div className="border-b bg-muted/30 px-4 py-2.5">
          <h2 className="text-sm font-medium">{t('userProfile.passwordForm.title')}</h2>
        </div>
        <div className="p-4">
          <PasswordChangeForm />
        </div>
      </div>
    </div>
  );
}

export default function UserProfilePage() {
  return (
    <ProtectedRoute>
      <UserProfilePageContent />
    </ProtectedRoute>
  );
}
