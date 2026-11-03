import type { Metadata } from 'next';
import localFont from 'next/font/local';
import './globals.css';
import { Toaster } from "@/components/ui/toaster";
import { LanguageProvider } from '@/context/LanguageContext';
import { AuthProvider } from '@/context/AuthContext';
import { AppClientLayout } from '@/components/layout/app-client-layout';
import { SettingsProvider } from '@/context/SettingsContext';
import { cn } from '@/lib/utils';

const googleSansFlex = localFont({
  src: './fonts/GoogleSansFlex-Variable.ttf',
  variable: '--font-google-sans-flex',
  weight: '100 1000',
  display: 'swap',
});

const notoSansSC = localFont({
  src: './fonts/NotoSansSC-Variable.ttf',
  variable: '--font-noto-sans-sc',
  weight: '100 900',
  display: 'swap',
});

const googleSansCode = localFont({
  src: [
    {
      path: './fonts/GoogleSansCode-Variable.ttf',
      weight: '300 800',
      style: 'normal',
    },
    {
      path: './fonts/GoogleSansCode-Italic-Variable.ttf',
      weight: '300 800',
      style: 'italic',
    },
  ],
  variable: '--font-google-sans-code',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'ClassIsland Entrance Test',
  description: 'Take the ClassIsland Entrance Test',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      suppressHydrationWarning
      className={cn(
        googleSansFlex.variable,
        notoSansSC.variable,
        googleSansCode.variable
      )}
    >
      <head>
        <script src="/security-init.js" />
        <script src="/theme-init.js" />
      </head>
      <body className="font-sans antialiased">
        <div className="relative z-0 flex flex-col min-h-screen">
          <SettingsProvider>
            <LanguageProvider>
              <AuthProvider>
                <AppClientLayout>
                  {children}
                </AppClientLayout>
              </AuthProvider>
            </LanguageProvider>
          </SettingsProvider>
          <Toaster />
        </div>
      </body>
    </html>
  );
}
