import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router'
import { z } from 'zod'

import { AuthCard } from '@/components/AuthCard'
import { api, ApiError, call } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  PasswordChecklist,
} from '@/components/PasswordChecklist'
import { PasswordInput } from '@/components/PasswordInput'
import { Button, buttonVariants } from '@/components/ui/button'
import { applyServerErrors } from '@/lib/errors'

const schema = z
  .object({
    password: z
      .string()
      .min(PASSWORD_MIN_LENGTH, { error: 'password.too_short' })
      .max(PASSWORD_MAX_LENGTH, { error: 'password.too_long' }),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    path: ['confirm'],
    error: 'validation.passwords_mismatch',
  })
type Values = z.infer<typeof schema>

/** FR-AUTH-02: the one-time token travels in the URL fragment (#token=...). */
export function SetPasswordPage() {
  const { t } = useTranslation('auth')
  const { hash } = useLocation()
  const token = new URLSearchParams(hash.slice(1)).get('token') ?? ''
  const navigate = useNavigate()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { password: '', confirm: '' },
  })

  const check = useQuery({
    queryKey: ['password-token', token],
    queryFn: () =>
      call(api.GET('/api/v1/auth/password/token/{token}', { params: { path: { token } } })),
    enabled: token !== '',
  })
  const save = useMutation({
    mutationFn: (values: Values) =>
      call(api.POST('/api/v1/auth/password/set', { body: { token, password: values.password } })),
    onSuccess: () => navigate('/sign-in?password=set', { replace: true }),
    onError: (error) => applyServerErrors(error, form.setError, ['password']),
  })

  const password = useWatch({ control: form.control, name: 'password' })
  const confirm = useWatch({ control: form.control, name: 'confirm' })

  // UX-07: a missing, used or expired link gets its own page that says what to do next.
  const linkInvalid =
    token === '' || (check.error instanceof ApiError && check.error.code === 'auth.token_invalid')
  if (linkInvalid) {
    return (
      <AuthCard
        title={t('setPassword.invalidTitle')}
        description={token === '' ? t('setPassword.missing') : t('setPassword.invalid')}
      >
        <div className="flex flex-col gap-4">
          <p className="text-sm">{t('setPassword.invalidNext')}</p>
          <Link className={buttonVariants()} to="/forgot-password">
            {t('setPassword.requestNew')}
          </Link>
          <Link className="text-sm text-primary underline underline-offset-4" to="/sign-in">
            {t('setPassword.backToSignIn')}
          </Link>
        </div>
      </AuthCard>
    )
  }

  let body
  if (check.isPending) body = <Loading variant="form" />
  else if (check.isError)
    body = <FormMessage error={check.error instanceof ApiError ? check.error.code : 'unknown'} />
  else {
    body = (
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          void form.handleSubmit((values) => {
            save.mutate(values)
          })(event)
        }}
      >
        <p className="text-sm text-muted-foreground">
          {t('setPassword.for', { email: check.data.email })}
        </p>
        <FormField
          label={t('setPassword.password')}
          required
          error={form.formState.errors.password?.message}
        >
          {(control) => (
            <PasswordInput
              {...control}
              autoComplete="new-password"
              {...form.register('password')}
            />
          )}
        </FormField>
        <FormField
          label={t('setPassword.confirm')}
          required
          error={form.formState.errors.confirm?.message}
        >
          {(control) => (
            <PasswordInput {...control} autoComplete="new-password" {...form.register('confirm')} />
          )}
        </FormField>
        <PasswordChecklist password={password} confirm={confirm} />
        {save.error instanceof ApiError && !form.formState.errors.password ? (
          <FormMessage error={save.error.code} />
        ) : null}
        <Button type="submit" disabled={save.isPending}>
          {t('setPassword.submit')}
        </Button>
      </form>
    )
  }

  const title =
    check.data?.purpose === 'reset' ? t('setPassword.titleReset') : t('setPassword.title')
  return <AuthCard title={title}>{body}</AuthCard>
}
