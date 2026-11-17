import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'
import { z } from 'zod'

import { api, call } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { applyServerErrors } from '@/lib/errors'

const schema = z
  .object({
    password: z
      .string()
      .min(12, { error: 'password.too_short' })
      .max(128, { error: 'password.too_long' }),
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

  let body
  if (token === '') body = <FormMessage error="auth.token_invalid" />
  else if (check.isPending) body = <Loading />
  else if (check.isError) body = <FormMessage error="auth.token_invalid" />
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
          error={form.formState.errors.password?.message}
          hint={t('setPassword.rules')}
        >
          {(control) => (
            <Input
              {...control}
              type="password"
              autoComplete="new-password"
              {...form.register('password')}
            />
          )}
        </FormField>
        <FormField label={t('setPassword.confirm')} error={form.formState.errors.confirm?.message}>
          {(control) => (
            <Input
              {...control}
              type="password"
              autoComplete="new-password"
              {...form.register('confirm')}
            />
          )}
        </FormField>
        {save.isError && !form.formState.errors.password ? (
          <FormMessage error="auth.token_invalid" />
        ) : null}
        <Button type="submit" disabled={save.isPending}>
          {t('setPassword.submit')}
        </Button>
      </form>
    )
  }

  const title =
    check.data?.purpose === 'reset' ? t('setPassword.titleReset') : t('setPassword.title')
  return (
    <section className="mx-auto mt-16 w-full max-w-sm rounded-xl border bg-card p-6 shadow-sm">
      <h1 className="mb-6 text-xl font-semibold">{title}</h1>
      {body}
    </section>
  )
}
