
"use client";

import type { ReactNode, Dispatch, SetStateAction } from 'react';
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { brandNameByLang } from '@/locales/brandNameByLang'; // Import new centralized brand names

interface AppSettings {
  brandName: string | null;
}

interface SettingsContextType {
  settings: AppSettings;
  setSetting: (key: keyof AppSettings, value: string) => void;
  isLoadingSettings: boolean;
}

const SETTINGS_STORAGE_KEY = 'appGlobalSettings';
const DEFAULT_BRAND_NAME = brandNameByLang.en; // Use English brand name from centralized source

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const SettingsProvider = ({ children }: { children: ReactNode }) => {
  const [settings, setSettings] = useState<AppSettings>({
    brandName: null, 
  });
  const [isLoadingSettings, setIsLoadingSettings] = useState(true);

  useEffect(() => {
    try {
      const storedSettings = localStorage.getItem(SETTINGS_STORAGE_KEY);
      if (storedSettings) {
        const parsedSettings = JSON.parse(storedSettings);
        setSettings(prev => ({ ...prev, ...parsedSettings }));
      } else {
        setSettings(prev => ({ ...prev, brandName: prev.brandName || DEFAULT_BRAND_NAME }));
      }
    } catch (error) {
      console.error("Error loading settings from localStorage:", error);
      setSettings(prev => ({ ...prev, brandName: prev.brandName || DEFAULT_BRAND_NAME }));
    }
    setIsLoadingSettings(false);
  }, []);

  const setSetting = useCallback((key: keyof AppSettings, value: string) => {
    setSettings(prevSettings => {
      const newSettings = { ...prevSettings, [key]: value };
      try {
        localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(newSettings));
      } catch (error) {
        console.error("Error saving settings to localStorage:", error);
      }
      return newSettings;
    });
  }, []);

  const effectiveSettings = {
    ...settings,
    brandName: settings.brandName || DEFAULT_BRAND_NAME,
  };

  return (
    <SettingsContext.Provider value={{ settings: effectiveSettings, setSetting, isLoadingSettings }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = (): SettingsContextType => {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};
