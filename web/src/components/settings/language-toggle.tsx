
"use client";

import * as React from "react";
import { Languages, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLanguage, type SupportedLanguage } from "@/context/LanguageContext";
import { useTranslation } from "@/hooks/useTranslation";
import type { TranslationKeys } from "@/locales/en"; 

const languageOptions: Array<{ code: SupportedLanguage; labelKey: TranslationKeys; nativeName: string }> = [
  { code: 'en', labelKey: 'settings.language.english', nativeName: 'English' },
  { code: 'zh', labelKey: 'settings.language.chinese', nativeName: '简体中文' },
  { code: 'zh-TW', labelKey: 'settings.language.traditionalChinese', nativeName: '繁體中文' }, // Added
  { code: 'ja', labelKey: 'settings.language.japanese', nativeName: '日本語' },
  { code: 'ko', labelKey: 'settings.language.korean', nativeName: '한국어' },
  { code: 'fr', labelKey: 'settings.language.french', nativeName: 'Français' },
  { code: 'de', labelKey: 'settings.language.german', nativeName: 'Deutsch' },
  { code: 'es', labelKey: 'settings.language.spanish', nativeName: 'Español' },
  { code: 'ar', labelKey: 'settings.language.arabic', nativeName: 'العربية' },
];

export function LanguageToggle() {
  const { language, setLanguage } = useLanguage();
  const { t } = useTranslation();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button 
          variant="ghost" 
          size="icon" 
          aria-label={t('settings.language.select')}
          title={t('settings.language.select')}
        >
          <Languages className="h-[1.2rem] w-[1.2rem]" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {languageOptions.map((option) => (
          <DropdownMenuItem 
            key={option.code} 
            onSelect={() => setLanguage(option.code)}
            className="flex justify-between items-center"
          >
            <span>{`${t(option.labelKey)} (${option.nativeName})`}</span>
            {language === option.code && <Check className="h-4 w-4 ml-2" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
