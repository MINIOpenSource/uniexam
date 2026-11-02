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
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Loader2 } from 'lucide-react';
import { useSettings } from '@/context/SettingsContext';

export function LoginForm() {
  const { login, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const { t } = useTranslation();
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const { settings } = useSettings();
  const currentBrandName = settings.brandName || t('app.brandName');

  const getLoginSchema = () => z.object({
    uid: z.string().min(3, { message: t('auth.form.validation.uidMinLength', {min: 3, max: 16})}).max(16, { message: t('auth.form.validation.uidMaxLength', {min: 3, max: 16})}),
    password: z.string().min(4, { message: t('auth.form.validation.passwordMinLength', {min: 4, max: 48}) }).max(48, { message: t('auth.form.validation.passwordMaxLength', {min: 4, max: 48}) }),
  });

  type LoginFormValues = z.infer<ReturnType<typeof getLoginSchema>>;

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(getLoginSchema()),
    defaultValues: { uid: '', password: '' },
  });

  React.useEffect(() => {
    form.trigger();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const onSubmit = async (data: LoginFormValues) => {
    setIsSubmitting(true);
    try {
      const response = await login(data.uid, data.password);

      if ('access_token' in response) {
        toast({ title: t('auth.toast.loginSuccess.title'), description: t('auth.toast.loginSuccess.description', { uid: data.uid }) });
        router.push('/');
      } else if (response.status_code === "WRONG" || String(response.status_code) === "401") {
        toast({ title: t('auth.toast.loginError.title'), description: response.message || t('auth.toast.loginError.wrongCredentials'), variant: "destructive" });
      } else if (String(response.status_code) === "429") {
        toast({ title: t('auth.toast.rateLimit.title'), description: response.message || t('auth.toast.rateLimit.description'), variant: "destructive" });
      } else {
        toast({ title: t('auth.toast.loginError.title'), description: response.message || t('auth.toast.loginError.generic'), variant: "destructive" });
      }
    } catch (error: any) {
      toast({ title: t('auth.toast.loginError.title'), description: error.message || t('auth.toast.loginError.network'), variant: "destructive" });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-sm rounded border bg-card">
      <div className="border-b px-5 py-3.5">
        <h1 className="text-base font-semibold text-foreground">
          {t('auth.login.title', { brandName: currentBrandName })}
        </h1>
      </div>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <div className="space-y-4 p-5">
          <div className="space-y-1.5">
            <Label htmlFor="uid" className="text-xs">{t('auth.form.uidLabel')}</Label>
            <Input id="uid" {...form.register("uid")} placeholder={t('auth.form.uidPlaceholder')} className="h-9 text-sm" />
            {form.formState.errors.uid && <p className="text-xs text-destructive">{form.formState.errors.uid.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password" className="text-xs">{t('auth.form.passwordLabel')}</Label>
            <Input id="password" type="password" {...form.register("password")} className="h-9 text-sm" />
            {form.formState.errors.password && <p className="text-xs text-destructive">{form.formState.errors.password.message}</p>}
          </div>
        </div>
        <div className="flex flex-col gap-3 border-t bg-muted/30 px-5 py-3.5">
          <Button type="submit" size="sm" className="w-full" disabled={authLoading || isSubmitting}>
            {(authLoading || isSubmitting) && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('auth.login.submitButton')}
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            {t('auth.login.noAccountPrompt')}{' '}
            <Link href="/auth/register" className="font-medium text-primary hover:underline">
              {t('auth.login.registerLink')}
            </Link>
          </p>
        </div>
      </form>
    </div>
  );
}
