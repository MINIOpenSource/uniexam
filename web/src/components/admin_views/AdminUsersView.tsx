"use client";

import type { User, UserPublicProfile, UserTag } from '@/types/auth';
import type { ConnectedDevice } from '@/types/exam';
import React, { useEffect, useState, useMemo, useTransition } from 'react';
import {
  fetchAdminUsers,
  updateAdminUser,
  revokeUserTokens,
} from '@/lib/admin-api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { useTranslation } from '@/hooks/useTranslation';
import { useToast } from '@/hooks/use-toast';
import { Loader2, SearchIcon } from 'lucide-react';
import { AdminUserCard } from './AdminUserCard';
import { cn } from '@/lib/utils';

interface AdminUsersViewProps {
  user: User | null;
  liveConnections?: ConnectedDevice[];
}

const ITEMS_PER_PAGE = 12;
const AVAILABLE_TAGS: UserTag[] = ['ADMIN', 'MANAGER', 'USER', 'BANNED'];

export function AdminUsersView({
  user,
  liveConnections = [],
}: AdminUsersViewProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [users, setUsers] = useState<UserPublicProfile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [isRefreshing, startRefreshTransition] = useTransition();

  // Edit User Modal state
  const [editingUser, setEditingUser] = useState<UserPublicProfile | null>(null);
  const [editNickname, setEditNickname] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editQq, setEditQq] = useState('');
  const [editTags, setEditTags] = useState<UserTag[]>(['USER']);
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  const loadUsers = async () => {
    if (!user?.token) {
      setError(t('auth.toast.sessionExpired.description'));
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const fetchedUsers = await fetchAdminUsers(user.token);
      setUsers(Array.isArray(fetchedUsers) ? fetchedUsers : []);
    } catch (e: any) {
      const errorMessage =
        e.message ||
        t('admin.users.toast.fetchError', {
          message: e.message || 'Unknown error',
        });
      setError(errorMessage);
      toast({
        title: t('admin.users.toast.fetchErrorTitle'),
        description: errorMessage,
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.token]);

  const handleRefresh = () => {
    startRefreshTransition(async () => {
      await loadUsers();
      toast({
        title: t('admin.users.toast.refreshedTitle'),
        description: t('admin.users.toast.refreshedDesc'),
      });
    });
  };

  const liveDevicesByUid = useMemo(() => {
    const map = new Map<string, ConnectedDevice[]>();
    for (const conn of liveConnections) {
      if (!conn.uid) continue;
      const arr = map.get(conn.uid) || [];
      arr.push(conn);
      map.set(conn.uid, arr);
    }
    return map;
  }, [liveConnections]);

  const filteredUsers = useMemo(() => {
    return users.filter(
      (u) =>
        u.uid.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (u.nickname &&
          u.nickname.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (u.email && u.email.toLowerCase().includes(searchTerm.toLowerCase()))
    );
  }, [users, searchTerm]);

  const paginatedUsers = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredUsers.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [filteredUsers, currentPage]);

  const totalPages = Math.ceil(filteredUsers.length / ITEMS_PER_PAGE);

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
    setCurrentPage(1);
  };

  const handleEditUser = (userToEdit: UserPublicProfile) => {
    setEditingUser(userToEdit);
    setEditNickname(userToEdit.nickname || '');
    setEditEmail(userToEdit.email || '');
    setEditQq(userToEdit.qq ? String(userToEdit.qq) : '');
    const normalizedTags = (userToEdit.tags || ['USER']).filter((tg) =>
      AVAILABLE_TAGS.includes(tg as UserTag)
    ) as UserTag[];
    setEditTags(normalizedTags.length > 0 ? normalizedTags : ['USER']);
  };

  const toggleTag = (tag: UserTag) => {
    setEditTags((prev) => {
      if (prev.includes(tag)) {
        const next = prev.filter((t) => t !== tag);
        return next.length > 0 ? next : ['USER'];
      }
      if (tag === 'BANNED') {
        return ['BANNED'];
      }
      return [...prev.filter((t) => t !== 'BANNED'), tag];
    });
  };

  const handleSaveUserEdit = async () => {
    if (!user?.token || !editingUser) return;
    setIsSavingEdit(true);
    try {
      const updated = await updateAdminUser(user.token, editingUser.uid, {
        nickname: editNickname.trim() || null,
        email: editEmail.trim() || null,
        qq: editQq.trim() ? String(editQq.trim()) : null,
        tags: editTags,
      });
      setUsers((prev) =>
        prev.map((u) => (u.uid === editingUser.uid ? updated : u))
      );
      toast({
        title: '用户信息已更新',
        description: `已成功保存 ${editingUser.uid} 的权限与资料设置。`,
      });
      setEditingUser(null);
    } catch (e: any) {
      toast({
        title: '保存用户失败',
        description: e.message || '更新用户信息时发生错误',
        variant: 'destructive',
      });
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleRevokeUserSessions = async (targetUser: UserPublicProfile) => {
    if (!user?.token) return;
    try {
      const res = await revokeUserTokens(user.token, targetUser.uid);
      toast({
        title: '已吊销用户会话',
        description: `账号 ${targetUser.uid} 的 ${res.invalidated_count} 个登录凭证及实时连接已断开。`,
      });
    } catch (e: any) {
      toast({
        title: '操作失败',
        description: e.message || '吊销会话失败',
        variant: 'destructive',
      });
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mr-2" />
        <span className="text-xs text-muted-foreground">
          {t('admin.users.loading')}
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded border border-destructive/40 bg-destructive/10 p-4 text-xs text-destructive">
        <div className="font-semibold">
          {t('admin.users.toast.fetchErrorTitle')}
        </div>
        <div>{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-3">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-foreground">
            {t('admin.users.view.title')}
          </h2>
          <span className="text-xs text-muted-foreground">
            ({t('admin.users.totalUsers', { count: filteredUsers.length })})
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              type="search"
              placeholder={t('admin.users.search.placeholder')}
              value={searchTerm}
              onChange={handleSearchChange}
              className="pl-8 h-8 text-xs w-56"
            />
          </div>
          <Button
            onClick={handleRefresh}
            variant="outline"
            size="sm"
            disabled={isRefreshing || !user?.token}
            className="h-8 text-xs"
          >
            {isRefreshing && (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            )}
            {t('admin.users.refreshButton')}
          </Button>
        </div>
      </div>

      {paginatedUsers.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {paginatedUsers.map((u) => (
            <AdminUserCard
              key={u.uid}
              userProfile={u}
              liveDevices={liveDevicesByUid.get(u.uid) || []}
              onEdit={handleEditUser}
              onRevokeSessions={handleRevokeUserSessions}
              isEditing={editingUser?.uid === u.uid}
            />
          ))}
        </div>
      ) : (
        <div className="rounded border bg-card py-10 text-center text-xs text-muted-foreground">
          {searchTerm ? t('admin.users.noResults') : t('admin.users.noUsers')}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-3 border-t text-xs">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
            disabled={currentPage === 1 || isRefreshing}
          >
            {t('admin.questionBankManager.pagination.previous')}
          </Button>
          <span className="text-muted-foreground">
            {t('admin.questionBankManager.pagination.pageIndicator', {
              currentPage,
              totalPages,
            })}
          </span>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() =>
              setCurrentPage((prev) => Math.min(totalPages, prev + 1))
            }
            disabled={currentPage === totalPages || isRefreshing}
          >
            {t('admin.questionBankManager.pagination.next')}
          </Button>
        </div>
      )}

      {/* Edit User Modal */}
      <Dialog
        open={Boolean(editingUser)}
        onOpenChange={(open) => !open && setEditingUser(null)}
      >
        <DialogContent className="sm:max-w-md p-5">
          <DialogHeader className="border-b pb-3">
            <DialogTitle className="text-base font-semibold">
              编辑用户资料与角色权限 · {editingUser?.uid}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3.5 py-2 text-xs">
            <div className="space-y-1.5">
              <Label htmlFor="edit-nickname" className="text-xs">
                昵称 (Nickname)
              </Label>
              <Input
                id="edit-nickname"
                value={editNickname}
                onChange={(e) => setEditNickname(e.target.value)}
                placeholder="输入用户昵称"
                className="h-8 text-xs"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="edit-email" className="text-xs">
                邮箱 (Email)
              </Label>
              <Input
                id="edit-email"
                type="email"
                value={editEmail}
                onChange={(e) => setEditEmail(e.target.value)}
                placeholder="user@example.com"
                className="h-8 text-xs"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="edit-qq" className="text-xs">
                QQ 号
              </Label>
              <Input
                id="edit-qq"
                value={editQq}
                onChange={(e) => setEditQq(e.target.value.replace(/\D/g, ''))}
                placeholder="输入数字 QQ 号"
                className="h-8 text-xs font-mono"
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">角色与状态标签 (Tags)</Label>
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {AVAILABLE_TAGS.map((tag) => {
                  const active = editTags.includes(tag);
                  return (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => toggleTag(tag)}
                      className={cn(
                        'rounded border px-2.5 py-1 text-xs font-mono font-semibold transition-colors',
                        active
                          ? tag === 'BANNED'
                            ? 'border-destructive bg-destructive text-destructive-foreground'
                            : 'border-primary bg-primary text-primary-foreground'
                          : 'border-border bg-muted/40 text-muted-foreground hover:bg-muted'
                      )}
                    >
                      {tag}
                    </button>
                  );
                })}
              </div>
              <p className="text-[11px] text-muted-foreground">
                选择 BANNED 将封禁该账号并自动断开其所有在线会话。
              </p>
            </div>
          </div>

          <DialogFooter className="border-t pt-3 flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => setEditingUser(null)}
              disabled={isSavingEdit}
            >
              取消
            </Button>
            <Button
              size="sm"
              className="h-8 text-xs"
              onClick={handleSaveUserEdit}
              disabled={isSavingEdit}
            >
              {isSavingEdit && (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              )}
              保存修改
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
