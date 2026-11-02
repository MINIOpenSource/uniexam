"use client";

import type { ReactNode } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import { useSettings } from '@/context/SettingsContext';
import { useTranslation } from '@/hooks/useTranslation';
import { ThemeToggle } from '@/components/settings/theme-toggle';
import { LanguageToggle } from '@/components/settings/language-toggle';
import { SecurityShieldProvider } from '@/components/security/security-shield';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

export function AppClientLayout({ children }: { children: ReactNode }) {
  const { user, logout, isLoading } = useAuth();
  const { settings } = useSettings();
  const { t } = useTranslation();
  const currentBrandName = settings.brandName || t('app.brandName');
  const pathname = usePathname();

  const isAuthPage = pathname.startsWith('/auth/');
  const isUserProfilePage = pathname.startsWith('/user/profile');
  const showGenericHeader = isAuthPage || isUserProfilePage;

  return (
    <SecurityShieldProvider>
      {showGenericHeader && (
        <header className="sticky top-0 z-30 flex h-12 items-center justify-between border-b bg-card px-4">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-sm font-semibold text-foreground hover:underline">
              {currentBrandName}
            </Link>
            {isUserProfilePage && user && (
              <>
                <span className="text-muted-foreground">/</span>
                <span className="text-sm text-foreground">{t('userProfile.pageTitle')}</span>
              </>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            <ThemeToggle />
            <LanguageToggle />
            {isLoading ? (
              <span className="text-xs text-muted-foreground">{t('auth.status.loading')}</span>
            ) : user && isUserProfilePage ? (
              <>
                <Link href="/" passHref>
                  <Button variant="outline" size="sm" className="h-8 text-xs">
                    {t('userCenter.backToHome')}
                  </Button>
                </Link>
                <Button variant="ghost" size="sm" onClick={logout} className="h-8 text-xs">
                  {t('auth.nav.logout')}
                </Button>
              </>
            ) : !user && isAuthPage ? (
              <>
                <Link href="/auth/login" passHref>
                  <Button variant="ghost" size="sm" className="h-8 text-xs">
                    {t('auth.nav.login')}
                  </Button>
                </Link>
                <Link href="/auth/register" passHref>
                  <Button variant="outline" size="sm" className="h-8 text-xs">
                    {t('auth.nav.register')}
                  </Button>
                </Link>
              </>
            ) : null}
          </div>
        </header>
      )}

      <div className={cn("flex-grow flex flex-col")}>
        {children}
      </div>
    </SecurityShieldProvider>
  );
}
