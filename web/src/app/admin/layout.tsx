
"use client";
import type { ReactNode } from 'react';
import Link from 'next/link';
import { HomeIcon, ListOrderedIcon, LibraryIcon, SettingsIcon, UserIcon } from 'lucide-react'; // Added UserIcon
import { useSettings } from '@/context/SettingsContext';
import { useTranslation, type TranslationKeys } from '@/hooks/useTranslation';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  SidebarProvider,
  Sidebar,
  SidebarHeader,
  SidebarTrigger,
  SidebarContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarFooter,
  SidebarInset,
} from '@/components/ui/sidebar';
import { useIsMobile } from '@/hooks/use-mobile';
import { usePathname } from 'next/navigation';
import React from 'react';
import { ThemeToggle } from '@/components/settings/theme-toggle';
import { LanguageToggle } from '@/components/settings/language-toggle';
import { cn } from '@/lib/utils';
import { ProtectedRoute } from '@/context/AuthContext';


type NavItemLink = {
  type: "link";
  href: string;
  icon: React.ElementType;
  labelKey: TranslationKeys;
  exact?: boolean;
};

type NavItemAccordion = {
  type: "accordion";
  icon: React.ElementType;
  labelKey: TranslationKeys;
  basePath: string;
  subItems: Array<{ href: string; labelKey: TranslationKeys; exact?: boolean }>;
};

type NavItem = NavItemLink | NavItemAccordion;

export default function AdminLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { settings } = useSettings();
  const isMobile = useIsMobile();
  const pathname = usePathname();
  const currentBrandName = settings.brandName || t('app.brandName');

  const navItems = React.useMemo<NavItem[]>(() => [
    { type: "link", href: "/admin", icon: HomeIcon, labelKey: 'admin.nav.home', exact: true },
    { type: "link", href: "/admin/papers", icon: ListOrderedIcon, labelKey: 'admin.nav.examPapers' },
    {
      type: "accordion",
      icon: LibraryIcon,
      labelKey: 'admin.nav.questionBanks',
      basePath: "/admin/question-banks",
      subItems: [
        { href: "/admin/question-banks/easy", labelKey: 'admin.nav.questionBanks.easy' },
        { href: "/admin/question-banks/hybrid", labelKey: 'admin.nav.questionBanks.hybrid' },
        { href: "/admin/question-banks/hard", labelKey: 'admin.nav.questionBanks.hard' },
      ]
    },
    { type: "link", href: "/admin/users", icon: UserIcon, labelKey: 'admin.nav.users' }, // New users link
    { type: "link", href: "/admin/settings", icon: SettingsIcon, labelKey: 'admin.nav.settings' },
  ], []);

  const initialSidebarOpen = React.useMemo(() => {
    if (typeof window === 'undefined') return true;
    return !isMobile;
  }, [isMobile]);

  return (
    <ProtectedRoute> {/* Protect the entire admin layout */}
      <SidebarProvider defaultOpen={initialSidebarOpen}>
        <Sidebar className="h-full max-h-screen flex-col" variant="floating" collapsible="icon">
          <SidebarHeader className="p-4 flex items-center justify-between">
            <Link href="/admin" className="flex items-center gap-2 shrink-0" title={currentBrandName}>
              <img
                src="/brand-mark.svg"
                alt=""
                aria-hidden="true"
                className="size-6 shrink-0 group-data-[collapsible=icon]:size-8"
              />
              <span className="text-lg font-semibold group-data-[collapsible=icon]:hidden">{currentBrandName}</span>
            </Link>
            <SidebarTrigger className="hidden md:flex ml-auto" />
          </SidebarHeader>
          <SidebarContent>
            <SidebarMenu>
              {navItems.map((item) => {
                 const isLinkActive = (href: string, exact?: boolean) => exact ? pathname === href : pathname.startsWith(href);

                if (item.type === "link") {
                  return (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton
                        asChild
                        isActive={isLinkActive(item.href, item.exact)}
                        tooltip={{ children: t(item.labelKey), side: "right", sideOffset: 8 }}
                        className="h-10"
                      >
                        <Link href={item.href}>
                          <item.icon />
                          <span>{t(item.labelKey)}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                }
                if (item.type === "accordion") {
                  const isAccordionActive = item.subItems.some(sub => isLinkActive(sub.href, sub.exact));
                  return (
                    <SidebarMenuItem key={item.basePath} className="group-data-[collapsible=icon]:p-0">
                       <Accordion type="single" collapsible defaultValue={isAccordionActive ? item.basePath : undefined} className="w-full group-data-[collapsible=icon]:p-0">
                        <AccordionItem value={item.basePath} className="border-b-0 group-data-[collapsible=icon]:p-0">
                          <TooltipProvider delayDuration={0}>
                            <Tooltip>
                              <TooltipTrigger asChild disabled={isMobile}>
                                <AccordionTrigger
                                  className={cn(
                                    "flex w-full items-center gap-2 rounded-md p-2 text-left text-sm outline-none ring-sidebar-ring transition-all hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 active:bg-sidebar-accent active:text-sidebar-accent-foreground disabled:pointer-events-none disabled:opacity-50 group-has-[[data-sidebar=menu-action]]/menu-item:pr-8 aria-disabled:pointer-events-none aria-disabled:opacity-50 h-10",
                                    "group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:p-2 group-data-[collapsible=icon]:justify-center",
                                    isAccordionActive && "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                                  )}
                                >
                                  <item.icon className={cn("group-data-[collapsible=icon]:size-5")}/>
                                  <span className="truncate group-data-[collapsible=icon]:hidden">{t(item.labelKey)}</span>
                                </AccordionTrigger>
                              </TooltipTrigger>
                              <TooltipContent side="right" align="center" sideOffset={8} className="group-data-[state=expanded]:hidden">
                                {t(item.labelKey)}
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                          <AccordionContent className="group-data-[collapsible=icon]:hidden pl-4 pr-2 py-1 space-y-0.5">
                            {item.subItems.map(subItem => (
                              <Link
                                key={subItem.href}
                                href={subItem.href}
                                className={cn(
                                  "block rounded-md px-3 py-2 text-sm hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                                  isLinkActive(subItem.href, subItem.exact) && "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                                )}
                              >
                                {t(subItem.labelKey)}
                              </Link>
                            ))}
                          </AccordionContent>
                        </AccordionItem>
                      </Accordion>
                    </SidebarMenuItem>
                  );
                }
                return null;
              })}
            </SidebarMenu>
          </SidebarContent>
          <SidebarFooter className="p-2 border-t group-data-[collapsible=icon]:hidden">
          </SidebarFooter>
        </Sidebar>
        <SidebarInset className="flex flex-col min-h-screen">
          <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background/80 backdrop-blur-sm px-4 sm:px-6">
            <SidebarTrigger className="md:hidden" />
            <h1 className="text-xl font-semibold">{t('admin.layout.title', { brandName: currentBrandName })}</h1>
            <div className="ml-auto flex items-center gap-2">
              <ThemeToggle />
              <LanguageToggle />
            </div>
          </header>
          <main className="flex-1 overflow-auto p-4 sm:px-6 sm:py-4 md:gap-8">
            {children}
          </main>
        </SidebarInset>
      </SidebarProvider>
    </ProtectedRoute>
  );
}
