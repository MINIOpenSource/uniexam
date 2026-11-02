
"use client";
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from '@/hooks/useTranslation';
import { updateUserProfile } from '@/lib/api';
import type { UserProfileUpdate, UserPublicProfile } from '@/types/auth';
import { Loader2, SaveIcon } from 'lucide-react';

export function ProfileUpdateForm() {
  const { user, isLoading: authLoading, fetchUserProfile, updateLocalUserProfile } = useAuth();
  const { toast } = useToast();
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const getProfileUpdateSchema = () => z.object({
    nickname: z.string().max(50, { message: t('auth.form.validation.nicknameMaxLength', { max: 50 }) }).optional().or(z.literal('')),
    email: z.string().email({ message: t('auth.form.validation.emailInvalid') }).optional().or(z.literal('')),
    qq: z.string().regex(/^[1-9][0-9]{4,14}$/, { message: t('auth.form.validation.qqInvalid') }).optional().or(z.literal('')),
  });

  type ProfileUpdateFormValues = z.infer<ReturnType<typeof getProfileUpdateSchema>>;

  const form = useForm<ProfileUpdateFormValues>({
    resolver: zodResolver(getProfileUpdateSchema()),
    defaultValues: {
      nickname: user?.profile?.nickname || '',
      email: user?.profile?.email || '',
      qq: user?.profile?.qq || '',
    },
  });

  React.useEffect(() => {
    form.reset({
      nickname: user?.profile?.nickname || '',
      email: user?.profile?.email || '',
      qq: user?.profile?.qq || '',
    });
  }, [user, form.reset]);

  React.useEffect(() => {
    form.trigger();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const onSubmit = async (data: ProfileUpdateFormValues) => {
    if (!user?.token) {
      toast({ title: t('auth.toast.sessionExpired.title'), description: t('auth.toast.sessionExpired.description'), variant: "destructive" });
      return;
    }
    setIsSubmitting(true);
    const payload: UserProfileUpdate = {
      nickname: data.nickname || null, // Send null if empty for backend
      email: data.email || null,
      qq: data.qq || null,
    };

    try {
      const updatedProfile: UserPublicProfile = await updateUserProfile(user.token, payload);
      updateLocalUserProfile(updatedProfile); // Update profile in AuthContext
      toast({ title: t('userProfile.toast.updateSuccess.title'), description: t('userProfile.toast.updateSuccess.description') });
    } catch (error: any) {
      toast({ title: t('userProfile.toast.updateError.title'), description: error.message || t('userProfile.toast.updateError.generic'), variant: "destructive" });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="nickname" className="text-xs font-medium">{t('auth.form.nicknameLabel')}</Label>
        <Input id="nickname" {...form.register("nickname")} placeholder={t('auth.form.nicknamePlaceholder')} className="h-9 text-sm" />
        {form.formState.errors.nickname && <p className="text-xs text-destructive">{form.formState.errors.nickname.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="email" className="text-xs font-medium">{t('auth.form.emailLabel')}</Label>
        <Input id="email" type="email" {...form.register("email")} placeholder={t('auth.form.emailPlaceholder')} className="h-9 text-sm" />
        {form.formState.errors.email && <p className="text-xs text-destructive">{form.formState.errors.email.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="qq" className="text-xs font-medium">{t('auth.form.qqLabel')}</Label>
        <Input id="qq" {...form.register("qq")} placeholder={t('auth.form.qqPlaceholder')} className="h-9 text-sm" />
        {form.formState.errors.qq && <p className="text-xs text-destructive">{form.formState.errors.qq.message}</p>}
      </div>
      <Button type="submit" size="sm" disabled={authLoading || isSubmitting}>
        {(authLoading || isSubmitting) && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {t('userProfile.updateForm.submitButton')}
      </Button>
    </form>
  );
}
