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

export function RegisterForm() {
  const { register, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const { t } = useTranslation();
  const router = useRouter();
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const { settings } = useSettings();
  const currentBrandName = settings.brandName || t('app.brandName');

  const getRegisterSchema = () => z.object({
    uid: z.string()
      .min(5, { message: t('auth.form.validation.uidMinLength', {min: 5, max: 16})})
      .max(16, { message: t('auth.form.validation.uidMaxLength', {min: 5, max: 16})}),
    password: z.string()
      .min(8, { message: t('auth.form.validation.passwordMinLength', {min: 8, max: 48}) })
      .max(48, { message: t('auth.form.validation.passwordMaxLength', {min: 8, max: 48}) }),
    confirmPassword: z.string(),
    nickname: z.string().max(50, {message: t('auth.form.validation.nicknameMaxLength', {max: 50})}).optional().or(z.literal('')),
    email: z.string().email({ message: t('auth.form.validation.emailInvalid') }).optional().or(z.literal('')),
    qq: z.string().regex(/^[1-9][0-9]{4,14}$/, { message: t('auth.form.validation.qqInvalid') }).optional().or(z.literal('')),
  }).refine(data => data.password === data.confirmPassword, {
    message: t('auth.form.validation.passwordsDontMatch'),
    path: ["confirmPassword"],
  });

  type RegisterFormValues = z.infer<ReturnType<typeof getRegisterSchema>>;

  const form = useForm<RegisterFormValues>({
    resolver: zodResolver(getRegisterSchema()),
    defaultValues: { uid: '', password: '', confirmPassword: '', nickname: '', email: '', qq: '' },
  });

  React.useEffect(() => {
    form.trigger();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const onSubmit = async (data: RegisterFormValues) => {
    setIsSubmitting(true);
    try {
      const response = await register(
        data.uid,
        data.password,
        data.nickname || undefined,
        data.email || undefined,
        data.qq || undefined
      );

      if ('access_token' in response) {
        toast({ title: t('auth.toast.registerSuccess.title'), description: t('auth.toast.registerSuccess.description', { uid: data.uid }) });
        router.push('/auth/login');
      } else if (response.status_code === "DUPLICATE" || String(response.status_code) === "409") {
        toast({ title: t('auth.toast.registerError.title'), description: response.message || t('auth.toast.registerError.duplicateUid'), variant: "destructive" });
      } else if (String(response.status_code) === "429") {
        toast({ title: t('auth.toast.rateLimit.title'), description: response.message || t('auth.toast.rateLimit.description'), variant: "destructive" });
      } else {
        toast({ title: t('auth.toast.registerError.title'), description: response.message || t('auth.toast.registerError.generic'), variant: "destructive" });
      }
    } catch (error: any) {
      toast({ title: t('auth.toast.registerError.title'), description: error.message || t('auth.toast.registerError.network'), variant: "destructive" });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-sm rounded border bg-card">
      <div className="border-b px-5 py-3.5">
        <h1 className="text-base font-semibold text-foreground">
          {t('auth.register.title', { brandName: currentBrandName })}
        </h1>
      </div>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <div className="space-y-3.5 p-5">
          <div className="space-y-1">
            <Label htmlFor="uid" className="text-xs">{t('auth.form.uidLabel')}</Label>
            <Input id="uid" {...form.register("uid")} placeholder={t('auth.form.uidPlaceholder')} className="h-9 text-sm" />
            {form.formState.errors.uid && <p className="text-xs text-destructive">{form.formState.errors.uid.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="password" className="text-xs">{t('auth.form.passwordLabel')}</Label>
            <Input id="password" type="password" {...form.register("password")} className="h-9 text-sm" />
            {form.formState.errors.password && <p className="text-xs text-destructive">{form.formState.errors.password.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="confirmPassword" className="text-xs">{t('auth.form.confirmPasswordLabel')}</Label>
            <Input id="confirmPassword" type="password" {...form.register("confirmPassword")} className="h-9 text-sm" />
            {form.formState.errors.confirmPassword && <p className="text-xs text-destructive">{form.formState.errors.confirmPassword.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="nickname" className="text-xs">{t('auth.form.nicknameLabel')}</Label>
            <Input id="nickname" {...form.register("nickname")} placeholder={t('auth.form.nicknamePlaceholder')} className="h-9 text-sm" />
            {form.formState.errors.nickname && <p className="text-xs text-destructive">{form.formState.errors.nickname.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="email" className="text-xs">{t('auth.form.emailLabel')}</Label>
            <Input id="email" type="email" {...form.register("email")} placeholder={t('auth.form.emailPlaceholder')} className="h-9 text-sm" />
            {form.formState.errors.email && <p className="text-xs text-destructive">{form.formState.errors.email.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="qq" className="text-xs">{t('auth.form.qqLabel')}</Label>
            <Input id="qq" {...form.register("qq")} placeholder={t('auth.form.qqPlaceholder')} className="h-9 text-sm" />
            {form.formState.errors.qq && <p className="text-xs text-destructive">{form.formState.errors.qq.message}</p>}
          </div>
        </div>
        <div className="flex flex-col gap-3 border-t bg-muted/30 px-5 py-3.5">
          <Button type="submit" size="sm" className="w-full" disabled={authLoading || isSubmitting}>
            {(authLoading || isSubmitting) && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('auth.register.submitButton')}
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            {t('auth.register.hasAccountPrompt')}{' '}
            <Link href="/auth/login" className="font-medium text-primary hover:underline">
              {t('auth.register.loginLink')}
            </Link>
          </p>
        </div>
      </form>
    </div>
  );
}
