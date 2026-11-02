"use client";
import React from 'react';
import {
  HomeIcon,
  ListOrderedIcon,
  LibraryIcon,
  SettingsIcon,
  UserIcon as UserIconLucide,
  ActivityIcon,
} from 'lucide-react';
import { useTranslation, type TranslationKeys } from '@/hooks/useTranslation';
import type { DifficultyLevel } from '@/types/auth';
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
  Sidebar,
  SidebarHeader,
  SidebarTrigger,
  SidebarContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarFooter,
} from '@/components/ui/sidebar';
import { useIsMobile } from '@/hooks/use-mobile';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type AdminSectionId =
  | 'home'
  | 'liveMonitor'
  | 'papers'
  | 'questionBanks'
  | 'users'
  | 'settings';

type NavItemLink = {
  type: "link";
  id: AdminSectionId;
  icon: React.ElementType;
  labelKey?: TranslationKeys;
  customLabel?: string;
  badgeCount?: number;
  exact?: boolean;
};

type NavItemAccordion = {
  type: "accordion";
  id: AdminSectionId;
  icon: React.ElementType;
  labelKey: TranslationKeys;
  basePathTrigger: string;
  subItems: Array<{ id: string; difficulty: DifficultyLevel; labelKey: TranslationKeys; exact?: boolean }>;
};

type NavItem = NavItemLink | NavItemAccordion;

interface AdminSidebarProps {
  currentBrandName: string;
  onNavigate: (section: AdminSectionId) => void;
  onNavigateToDifficultyBank?: (difficulty: DifficultyLevel) => void;
  selectedSection: AdminSectionId | null;
  selectedDifficultyBank?: DifficultyLevel | null;
  liveConnectionCount?: number;
}

export function AdminSidebar({
  currentBrandName,
  onNavigate,
  onNavigateToDifficultyBank,
  selectedSection,
  selectedDifficultyBank,
  liveConnectionCount = 0,
}: AdminSidebarProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();

  const navItems = React.useMemo<NavItem[]>(() => [
    { type: "link", id: "home", icon: HomeIcon, labelKey: 'admin.nav.home', exact: true },
    {
      type: "link",
      id: "liveMonitor",
      icon: ActivityIcon,
      customLabel: "实时前端监控 (Live)",
      badgeCount: liveConnectionCount,
    },
    { type: "link", id: "papers", icon: ListOrderedIcon, labelKey: 'admin.nav.examPapers' },
    {
      type: "accordion",
      id: "questionBanks",
      icon: LibraryIcon,
      labelKey: 'admin.nav.questionBanks',
      basePathTrigger: "questionBanks",
      subItems: [
        { id: "qb-easy", difficulty: 'easy', labelKey: 'admin.nav.questionBanks.easy' },
        { id: "qb-hybrid", difficulty: 'hybrid', labelKey: 'admin.nav.questionBanks.hybrid' },
        { id: "qb-hard", difficulty: 'hard', labelKey: 'admin.nav.questionBanks.hard' },
      ]
    },
    { type: "link", id: "users", icon: UserIconLucide, labelKey: 'admin.nav.users' },
    { type: "link", id: "settings", icon: SettingsIcon, labelKey: 'admin.nav.settings' },
  ], [liveConnectionCount]);

  const isSubItemActive = (difficulty: DifficultyLevel) => {
    return selectedSection === 'questionBanks' && selectedDifficultyBank === difficulty;
  };

  return (
    <Sidebar className="h-full max-h-screen flex-col border-r bg-card" collapsible="icon">
      <SidebarHeader className="p-3 border-b flex items-center justify-between">
        <div onClick={() => onNavigate('home')} className="flex items-center gap-2 shrink-0 cursor-pointer" title={currentBrandName}>
          <span className="text-sm font-semibold group-data-[collapsible=icon]:hidden">{currentBrandName}</span>
        </div>
        <SidebarTrigger className="hidden md:flex ml-auto" />
      </SidebarHeader>
      <SidebarContent>
        <SidebarMenu>
          {navItems.map((item) => {
            if (item.type === "link") {
              const label = item.customLabel || (item.labelKey ? t(item.labelKey) : item.id);
              return (
                <SidebarMenuItem key={item.id}>
                  <SidebarMenuButton
                    onClick={() => onNavigate(item.id)}
                    isActive={selectedSection === item.id}
                    tooltip={{ children: label, side: "right", sideOffset: 8 }}
                    className="h-10 justify-between"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <item.icon className="shrink-0 h-4 w-4" />
                      <span className="truncate">{label}</span>
                    </div>
                    {typeof item.badgeCount === 'number' && (
                      <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/40 px-1.5 py-0.5 text-[10px] font-mono font-semibold text-emerald-600 dark:text-emerald-400 group-data-[collapsible=icon]:hidden">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                        {item.badgeCount}
                      </span>
                    )}
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            }
            if (item.type === "accordion" && onNavigateToDifficultyBank) {
              const isAccordionActive = selectedSection === item.id;
              return (
                <SidebarMenuItem key={item.id} className="group-data-[collapsible=icon]:p-0">
                   <Accordion type="single" collapsible defaultValue={isAccordionActive ? item.basePathTrigger : undefined} className="w-full group-data-[collapsible=icon]:p-0">
                    <AccordionItem value={item.basePathTrigger} className="border-b-0 group-data-[collapsible=icon]:p-0">
                      <TooltipProvider delayDuration={0}>
                        <Tooltip>
                          <TooltipTrigger asChild disabled={isMobile}>
                            <AccordionTrigger
                              onClick={() => onNavigate(item.id)}
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
                          <Button
                            key={subItem.id}
                            variant="ghost"
                            onClick={() => onNavigateToDifficultyBank(subItem.difficulty)}
                            className={cn(
                              "w-full justify-start block rounded-md px-3 py-2 text-sm hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                              isSubItemActive(subItem.difficulty) && "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                            )}
                          >
                            {t(subItem.labelKey)}
                          </Button>
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
  );
}
