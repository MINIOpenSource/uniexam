import React from 'react';
import { useLanguage, type SupportedLanguage } from '@/context/LanguageContext';
import { enTranslations, type TranslationKeys as AppTranslationKeys } from '@/locales/en/index';
import { zhTranslations } from '@/locales/zh/index';
import { jaTranslations } from '@/locales/ja/index';
import { koTranslations } from '@/locales/ko/index';
import { frTranslations } from '@/locales/fr/index';
import { deTranslations } from '@/locales/de/index';
import { esTranslations } from '@/locales/es/index';
import { arTranslations } from '@/locales/ar/index';
import { zhTWTranslations } from '@/locales/zh-TW/index';
import { brandNameByLang, BRAND_NAME_TRANSLATION_KEY } from '@/locales/brandNameByLang';

export type TranslationKeys = AppTranslationKeys;

const translationsMap: Record<SupportedLanguage, Partial<Record<string, string>>> = {
  en: enTranslations,
  zh: zhTranslations,
  ja: jaTranslations,
  ko: koTranslations,
  fr: frTranslations,
  de: deTranslations,
  es: esTranslations,
  ar: arTranslations,
  'zh-TW': zhTWTranslations,
};

export const useTranslation = () => {
  const { language } = useLanguage();

  const t = React.useCallback((key: TranslationKeys, params?: Record<string, string | number>): string => {
    if (key === BRAND_NAME_TRANSLATION_KEY) {
      return brandNameByLang[language] || brandNameByLang.en;
    }

    let translation = translationsMap[language]?.[key] || translationsMap['en']?.[key];

    if (translation === undefined || (translation === key && language !== 'en' && translationsMap['en']?.[key] === undefined)) {
      return key;
    }

    if (translation === key && language !== 'en' && translationsMap['en']?.[key]) {
      translation = translationsMap['en'][key]!;
    }

    if (params) {
      Object.entries(params).forEach(([paramKey, value]) => {
        translation = translation!.replace(new RegExp(`{${paramKey}}`, 'g'), String(value));
      });
    }
    return translation!;
  }, [language]);

  return { t, currentLanguage: language };
};
