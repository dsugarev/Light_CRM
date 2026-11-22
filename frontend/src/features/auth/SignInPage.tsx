import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'

import { AuthCard } from '@/components/AuthCard'
import { api, ApiError, call } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/PasswordInput'
import { Spinner } from '@/components/Spinner'
import { isLocale } from '@/i18n'
import { formatDateTime } from '@/lib/format'
import { storeLocale } from '@/lib/locale'
import { useLocale } from '@/lib/useLocale'

import { safeNext } from './safeNext'
import { SESSION_EXPIRED_KEY } from './sessionExpiry'
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

  // FR-AUTH-07: after a correct password, accounts with two-factor sign-in need a code.
  const [codeStep, setCodeStep] = useState(false)
  const [code, setCode] = useState('')
  const finish = async (result: { user: { locale: string } }) => {
    if (isLocale(result.user.locale)) {
      storeLocale(result.user.locale)
      await i18n.changeLanguage(result.user.locale)
    }
    // A new session: a later sign-out is no longer an expiry (FN-04).
    queryClient.setQueryData(SESSION_EXPIRED_KEY, false)
    await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })
    await navigate(next, { replace: true })
  }
  // UX-06: how long until the next try, rounded up to whole minutes (set when the error arrives).
  const [lockedMinutes, setLockedMinutes] = useState(0)
  const signIn = useMutation({
    mutationFn: (values: Values) => call(api.POST('/api/v1/auth/login', { body: values })),
    onSuccess: finish,
    onError: (failure) => {
      if (failure instanceof ApiError && failure.code === 'auth.mfa_required') setCodeStep(true)
      const until = failure instanceof ApiError ? failure.problem['locked_until'] : undefined
      setLockedMinutes(
        typeof until === 'string'
          ? Math.max(0, Math.ceil((new Date(until).getTime() - Date.now()) / 60_000))
          : 0,
      )
    },
  })
  const verify = useMutation({
    mutationFn: () => call(api.POST('/api/v1/auth/login/mfa', { body: { code: code.trim() } })),
    onSuccess: finish,
    onError: (failure) => {
      // The five-minute window passed: start again from the password.
      if (failure instanceof ApiError && failure.code === 'auth.session_expired') {
        setCodeStep(false)
        setCode('')
      }
    },
  })

  if (me) return <Navigate to={next} replace />

  if (codeStep) {
    const codeError = verify.error
    return (
      <AuthCard title={t('mfa.title')} description={t('mfa.hint')}>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (code.trim()) verify.mutate()
          }}
        >
          <FormMessage
            focusOnError
            error={codeError instanceof ApiError ? codeError.code : codeError ? 'unknown' : null}
          />
          <FormField label={t('mfa.code')} required>
            {(control) => (
              <Input
                {...control}
                autoFocus
                autoComplete="one-time-code"
                inputMode="text"
                maxLength={20}
                value={code}
                onChange={(event) => {
                  setCode(event.target.value)
                }}
              />
            )}
          </FormField>
          <Button
            type="submit"
            disabled={verify.isPending || code.trim() === ''}
            aria-busy={verify.isPending}
          >
            {verify.isPending ? <Spinner /> : null}
            {t('mfa.verify')}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setCodeStep(false)
              setCode('')
            }}
          >
            {t('mfa.back')}
          </Button>
        </form>
      </AuthCard>
    )
  }

  const error = signIn.error
  const lockedAt =
    error instanceof ApiError && typeof error.problem['locked_until'] === 'string'
      ? error.problem['locked_until']
      : undefined
  const lockedUntil = lockedAt ? formatDateTime(lockedAt, locale) : undefined

  return (
    <AuthCard title={t('signIn.title')}>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          void form.handleSubmit((values) => {
            signIn.mutate(values)
          })(event)
        }}
      >
        {params.get('expired') === '1' && !error ? (
          // FN-04: the session ended (timeout, sign-out elsewhere, deactivation).
          <FormMessage success={t('signIn.expired')} />
        ) : null}
        {params.get('password') === 'set' ? (
          <FormMessage success={t('signIn.passwordSet')} />
        ) : null}
        <FormMessage
          focusOnError
          error={error instanceof ApiError ? error.code : error ? 'unknown' : null}
          {...(lockedUntil ? { values: { time: lockedUntil } } : {})}
        />
        {lockedMinutes > 0 ? (
          <p className="text-sm text-muted-foreground">
            {t('signIn.lockedRemaining', { count: lockedMinutes })}
          </p>
        ) : null}
        <FormField label={t('signIn.email')} required error={form.formState.errors.email?.message}>
          {(control) => (
            <Input {...control} type="email" autoComplete="username" {...form.register('email')} />
          )}
        </FormField>
        <FormField
          label={t('signIn.password')}
          required
          error={form.formState.errors.password?.message}
        >
          {(control) => (
            <PasswordInput
              {...control}
              autoComplete="current-password"
              {...form.register('password')}
            />
          )}
        </FormField>
        <Button type="submit" disabled={signIn.isPending} aria-busy={signIn.isPending}>
          {signIn.isPending ? <Spinner /> : null}
          {signIn.isPending ? t('signIn.submitting') : t('signIn.submit')}
        </Button>
        <Link className="text-sm text-primary underline underline-offset-4" to="/forgot-password">
          {t('signIn.forgot')}
        </Link>
      </form>
    </AuthCard>
  )
}
