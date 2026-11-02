
'use client';

import type { Dispatch, ReactNode, SetStateAction } from 'react';
import React, { createContext, useContext, useEffect, useState } from 'react';

export type SupportedLanguage = 'en' | 'zh' | 'ja' | 'ko' | 'fr' | 'de' | 'es' | 'ar' | 'zh-TW';

interface LanguageContextType {
  language: SupportedLanguage;
  setLanguage: Dispatch<SetStateAction<SupportedLanguage>>;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export const LanguageProvider = ({ children }: { children: ReactNode }) => {
  const [language, setLanguage] = useState<SupportedLanguage>('en'); // Default to English

  useEffect(() => {
    const browserLang = navigator.language?.toLowerCase();
    if (browserLang?.startsWith('en')) {
      setLanguage('en');
    } else if (browserLang === 'zh-cn' || browserLang === 'zh') { // Simplified Chinese
      setLanguage('zh');
    } else if (browserLang === 'zh-tw' || browserLang === 'zh-hk' || browserLang === 'zh-hant') { // Traditional Chinese
      setLanguage('zh-TW');
    } else if (browserLang?.startsWith('ja')) {
      setLanguage('ja');
    } else if (browserLang?.startsWith('ko')) {
      setLanguage('ko');
    } else if (browserLang?.startsWith('fr')) {
      setLanguage('fr');
    } else if (browserLang?.startsWith('de')) {
      setLanguage('de');
    } else if (browserLang?.startsWith('es')) {
      setLanguage('es');
    } else if (browserLang?.startsWith('ar')) {
      setLanguage('ar');
    }
    // No explicit fallback here, initial state is 'en'
  }, []);

  useEffect(() => {
    // Update html lang attribute when language changes
    if (language === 'zh') {
        document.documentElement.lang = 'zh-CN';
    } else if (language === 'zh-TW') {
        document.documentElement.lang = 'zh-TW';
    } else {
        document.documentElement.lang = language;
    }
  }, [language]);


  return (
    <LanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = (): LanguageContextType => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};
