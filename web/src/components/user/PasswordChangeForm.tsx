
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
import { updateUserPassword } from '@/lib/api';
import type { UserPasswordUpdate } from '@/types/auth';
import { Loader2, KeyRoundIcon } from 'lucide-react';

export function PasswordChangeForm() {
  const { user, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  // OpenAPI schema: new_password min:8, max:48
  const getPasswordChangeSchema = () => z.object({
    current_password: z.string().min(1, { message: t('userProfile.passwordForm.validation.currentPasswordRequired') }),
    new_password: z.string().min(8, { message: t('auth.form.validation.passwordMinLength', { min: 8, max: 48 }) }).max(48, { message: t('auth.form.validation.passwordMaxLength', { min: 8, max: 48 }) }),
    confirm_new_password: z.string(),
  }).refine(data => data.new_password === data.confirm_new_password, {
    message: t('auth.form.validation.passwordsDontMatch'),
    path: ["confirm_new_password"],
  });

  type PasswordChangeFormValues = z.infer<ReturnType<typeof getPasswordChangeSchema>>;

  const form = useForm<PasswordChangeFormValues>({
    resolver: zodResolver(getPasswordChangeSchema()),
    defaultValues: { current_password: '', new_password: '', confirm_new_password: '' },
  });

  React.useEffect(() => {
    form.trigger();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const onSubmit = async (data: PasswordChangeFormValues) => {
    if (!user?.token) {
      toast({ title: t('auth.toast.sessionExpired.title'), description: t('auth.toast.sessionExpired.description'), variant: "destructive" });
      return;
    }
    setIsSubmitting(true);
    const payload: UserPasswordUpdate = {
      current_password: data.current_password,
      new_password: data.new_password,
    };

    try {
      await updateUserPassword(user.token, payload);
      toast({ title: t('userProfile.toast.passwordSuccess.title'), description: t('userProfile.toast.passwordSuccess.description') });
      form.reset(); // Clear form after successful password change
    } catch (error: any) {
      // Backend might return 401 for incorrect current_password, or 422 for other validation
      if (error.message && (error.message.includes('401') || error.message.toLowerCase().includes('incorrect current password'))) {
        toast({ title: t('userProfile.toast.passwordError.title'), description: t('userProfile.passwordForm.validation.currentPasswordIncorrect'), variant: "destructive" });
      } else if (error.message && (error.message.includes('422'))) {
         toast({ title: t('userProfile.toast.passwordError.title'), description: t('userProfile.toast.passwordError.validation'), variant: "destructive" });
      }
      else {
        toast({ title: t('userProfile.toast.passwordError.title'), description: error.message || t('userProfile.toast.passwordError.generic'), variant: "destructive" });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="current_password" className="text-xs font-medium">{t('userProfile.passwordForm.currentPasswordLabel')}</Label>
        <Input id="current_password" type="password" {...form.register("current_password")} placeholder="********" className="h-9 text-sm" />
        {form.formState.errors.current_password && <p className="text-xs text-destructive">{form.formState.errors.current_password.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="new_password" className="text-xs font-medium">{t('userProfile.passwordForm.newPasswordLabel')}</Label>
        <Input id="new_password" type="password" {...form.register("new_password")} placeholder="********" className="h-9 text-sm" />
        {form.formState.errors.new_password && <p className="text-xs text-destructive">{form.formState.errors.new_password.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="confirm_new_password" className="text-xs font-medium">{t('userProfile.passwordForm.confirmNewPasswordLabel')}</Label>
        <Input id="confirm_new_password" type="password" {...form.register("confirm_new_password")} placeholder="********" className="h-9 text-sm" />
        {form.formState.errors.confirm_new_password && <p className="text-xs text-destructive">{form.formState.errors.confirm_new_password.message}</p>}
      </div>
      <Button type="submit" size="sm" disabled={authLoading || isSubmitting}>
        {(authLoading || isSubmitting) && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {t('userProfile.passwordForm.submitButton')}
      </Button>
    </form>
  );
}
