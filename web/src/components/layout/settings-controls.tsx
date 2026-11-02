
"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/settings/theme-toggle";
import { LanguageToggle } from "@/components/settings/language-toggle";
import { useAuth } from "@/context/AuthContext"; // Import useAuth to check user state

export function SettingsControls() {
  const pathname = usePathname();
  const { user } = useAuth(); // Get user state

  // Hide if on:
  // 1. Root exam/user center page ('/') - Header is handled by page.tsx or ExamInfoBar or AppClientLayout.
  // 2. Admin pages ('/admin/*') - AdminLayout's header handles controls.
  // 3. Auth pages ('/auth/*') - AppClientLayout's header handles controls.
  // 4. User Profile page ('/user/profile') - AppClientLayout's header handles controls.
  if (pathname === "/" || pathname.startsWith("/admin") || pathname.startsWith("/auth") || pathname.startsWith("/user/profile")) {
    return null;
  }

  // For any other pages (if they exist in the future), render the controls in their usual fixed position.
  return (
    <div className="fixed top-4 right-4 z-50 flex items-center gap-2">
      <ThemeToggle />
      <LanguageToggle />
    </div>
  );
}
