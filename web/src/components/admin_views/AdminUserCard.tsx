"use client";

import type { UserPublicProfile } from '@/types/auth';
import type { ConnectedDevice } from '@/types/exam';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/hooks/useTranslation';
import { cn } from '@/lib/utils';
import { UserX } from 'lucide-react';

interface AdminUserCardProps {
  userProfile: UserPublicProfile;
  liveDevices?: ConnectedDevice[];
  onEdit: (user: UserPublicProfile) => void;
  onRevokeSessions?: (user: UserPublicProfile) => void;
  isEditing: boolean;
}

export function AdminUserCard({
  userProfile,
  liveDevices = [],
  onEdit,
  onRevokeSessions,
}: AdminUserCardProps) {
  const { t } = useTranslation();
  const isOnline = liveDevices.length > 0;
  const activeExamDev = liveDevices.find((d) => d.active_paper_id);
  const hasBlurIssue = liveDevices.some(
    (d) => d.window_focused === false || d.visibility_state === 'hidden'
  );

  return (
    <div
      className={cn(
        "flex flex-col justify-between rounded border bg-card p-3.5 text-xs transition-colors",
        isOnline && "border-emerald-500/40"
      )}
    >
      <div className="space-y-2">
        <div className="flex items-center justify-between border-b pb-2 gap-2">
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              className={cn(
                "h-2 w-2 rounded-full shrink-0",
                isOnline
                  ? hasBlurIssue
                    ? "bg-amber-500 animate-pulse"
                    : "bg-emerald-500 animate-pulse"
                  : "bg-muted-foreground/30"
              )}
              title={isOnline ? `${liveDevices.length} 台设备在线` : "离线"}
            />
            <span
              className="font-code-extrabold text-sm text-foreground break-all"
              title={userProfile.uid}
            >
              {userProfile.uid}
            </span>
          </div>
          {userProfile.nickname && (
            <span className="text-muted-foreground truncate max-w-[45%]">
              {userProfile.nickname}
            </span>
          )}
        </div>

        <div className="space-y-1 text-muted-foreground">
          {isOnline && (
            <div className="flex items-center justify-between gap-2 rounded bg-emerald-500/10 px-2 py-1 text-[11px] text-emerald-700 dark:text-emerald-300 font-mono">
              <span>在线终端: {liveDevices.length} 台</span>
              <span>
                {activeExamDev
                  ? `作答中 Q${(activeExamDev.current_question_index || 0) + 1}`
                  : hasBlurIssue
                  ? "窗口失焦"
                  : "焦点正常"}
              </span>
            </div>
          )}

          {userProfile.email && (
            <div className="flex justify-between gap-2">
              <span>{t('admin.users.table.email')}:</span>
              <span className="text-foreground break-all">{userProfile.email}</span>
            </div>
          )}
          {userProfile.qq && (
            <div className="flex justify-between gap-2">
              <span>{t('admin.users.table.qq')}:</span>
              <span className="font-code-extrabold text-foreground">{userProfile.qq}</span>
            </div>
          )}
          {userProfile.tags && userProfile.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-1">
              {userProfile.tags.map((tag) => (
                <span
                  key={tag}
                  className={cn(
                    "rounded border px-1.5 py-0.5 text-[11px] font-code-extrabold",
                    tag === 'ADMIN'
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : tag === 'BANNED'
                      ? "border-destructive/40 bg-destructive/10 text-destructive"
                      : "border-border bg-muted text-muted-foreground"
                  )}
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="mt-3 flex items-center justify-end gap-1.5 border-t pt-2.5">
        {onRevokeSessions && isOnline && (
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs text-destructive hover:text-destructive gap-1"
            onClick={() => onRevokeSessions(userProfile)}
            title="吊销该用户所有 Token 并踢下线"
          >
            <UserX className="h-3 w-3" />
            踢下线
          </Button>
        )}
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2.5 text-xs"
          onClick={() => onEdit(userProfile)}
        >
          {t('admin.users.editButton')}
        </Button>
      </div>
    </div>
  );
}
