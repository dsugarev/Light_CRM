import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'

import { api, ApiError, call } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { isLocale } from '@/i18n'
import { formatDateTime } from '@/lib/format'
import { storeLocale } from '@/lib/locale'
import { useLocale } from '@/lib/useLocale'

import { safeNext } from './safeNext'
import { ME_QUERY_KEY, useMe } from './useMe'

const schema = z.object({
  email: z.string().trim().min(1, { error: 'validation.required' }),
  password: z.string().min(1, { error: 'validation.required' }),
})
type Values = z.infer<typeof schema>

export function SignInPage() {
  const { t, i18n } = useTranslation('auth')
  const locale = useLocale()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: me } = useMe()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  })

  const signIn = useMutation({
    mutationFn: (values: Values) => call(api.POST('/api/v1/auth/login', { body: values })),
    onSuccess: async (result) => {
      if (isLocale(result.user.locale)) {
        storeLocale(result.user.locale)
        await i18n.changeLanguage(result.user.locale)
      }
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })
      await navigate(next, { replace: true })
    },
  })

  if (me) return <Navigate to={next} replace />

  const error = signIn.error
  const lockedUntil =
    error instanceof ApiError && typeof error.problem['locked_until'] === 'string'
      ? formatDateTime(error.problem['locked_until'], locale)
      : undefined

  return (
    <section className="mx-auto mt-16 w-full max-w-sm rounded-xl border bg-card p-6 shadow-sm">
      <h1 className="mb-6 text-xl font-semibold">{t('signIn.title')}</h1>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          void form.handleSubmit((values) => {
            signIn.mutate(values)
          })(event)
        }}
      >
        {params.get('password') === 'set' ? (
          <FormMessage success={t('signIn.passwordSet')} />
        ) : null}
        <FormMessage
          error={error instanceof ApiError ? error.code : error ? 'unknown' : null}
          {...(lockedUntil ? { values: { time: lockedUntil } } : {})}
        />
        <FormField label={t('signIn.email')} error={form.formState.errors.email?.message}>
          {(control) => (
            <Input {...control} type="email" autoComplete="username" {...form.register('email')} />
          )}
        </FormField>
        <FormField label={t('signIn.password')} error={form.formState.errors.password?.message}>
          {(control) => (
            <Input
              {...control}
              type="password"
              autoComplete="current-password"
              {...form.register('password')}
            />
          )}
        </FormField>
        <Button type="submit" disabled={signIn.isPending}>
          {signIn.isPending ? t('signIn.submitting') : t('signIn.submit')}
        </Button>
        <Link className="text-sm text-primary underline underline-offset-4" to="/forgot-password">
          {t('signIn.forgot')}
        </Link>
      </form>
    </section>
  )
}
