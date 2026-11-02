
"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/hooks/useTranslation";

export function ThemeToggle() {
  const [theme, setTheme] = React.useState<'light' | 'dark'>('light');
  const { t } = useTranslation();

  React.useEffect(() => {
    const storedTheme = localStorage.getItem("theme") as 'light' | 'dark' | null;
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    let initialTheme: 'light' | 'dark';
    if (storedTheme) {
      initialTheme = storedTheme;
    } else {
      initialTheme = systemPrefersDark ? 'dark' : 'light';
    }
    
    setTheme(initialTheme);
    // This ensures the classList is in sync if the script in layout.tsx didn't run or was overridden
    if (initialTheme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, []);

  const toggleTheme = () => {
    setTheme((prevTheme) => {
      const newTheme = prevTheme === "light" ? "dark" : "light";
      localStorage.setItem("theme", newTheme);
      if (newTheme === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
      return newTheme;
    });
  };

  const ariaLabel = theme === "light" 
    ? t('settings.theme.toggle.ariaLabel.toDark') 
    : t('settings.theme.toggle.ariaLabel.toLight');

  return (
    <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={ariaLabel}>
      {theme === "light" ? <Sun className="h-[1.2rem] w-[1.2rem]" /> : <Moon className="h-[1.2rem] w-[1.2rem]" />}
      <span className="sr-only">{ariaLabel}</span>
    </Button>
  );
}
