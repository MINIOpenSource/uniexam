
// src/locales/brandNameByLang.ts
import type { SupportedLanguage } from '@/context/LanguageContext';

export const brandNameByLang: Record<SupportedLanguage, string> = {
  en: 'ClassIsland',
  zh: 'ClassIsland', // TODO: Translate to Simplified Chinese
  ja: 'ClassIsland', // TODO: Translate to Japanese
  ko: 'ClassIsland', // TODO: Translate to Korean
  fr: 'ClassIsland', // TODO: Translate to French
  de: 'ClassIsland', // TODO: Translate to German
  es: 'ClassIsland', // TODO: Translate to Spanish
  ar: 'ClassIsland', // TODO: Translate to Arabic
  'zh-TW': 'ClassIsland', // TODO: Translate to Traditional Chinese
};

export const BRAND_NAME_TRANSLATION_KEY = 'app.brandName' as const;
