import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'

import { api, ApiError, call } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ME_QUERY_KEY, useMe, type Me } from '@/features/auth/useMe'
import { SUPPORTED_LOCALES } from '@/i18n'
import { applyServerErrors } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'
import { storeLocale } from '@/lib/locale'
import { useNotify } from '@/lib/notify'
import { useLocale } from '@/lib/useLocale'

import { MfaCard } from './MfaCard'

export function ProfilePage() {
  const { t } = useTranslation('profile')
  const { data: me } = useMe()
  if (!me) return <Loading />
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader title={t('title')} />
      {me.mfa_setup_required ? (
        <Alert>
          <AlertDescription>{t('mfa.required')}</AlertDescription>
        </Alert>
      ) : null}
      <MfaCard me={me} />
      {me.mfa_setup_required ? null : (
        <>
          <DetailsCard me={me} />
          <PasswordCard />
          <SessionsCard />
        </>
      )}
    </div>
  )
}

const detailsSchema = z.object({
  full_name: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .max(200, { error: 'validation.string_too_long' }),
  locale: z.enum(SUPPORTED_LOCALES),
})
type DetailsValues = z.infer<typeof detailsSchema>

function DetailsCard({ me }: { me: Me }) {
  const { t, i18n } = useTranslation('profile')
  const { t: tc } = useTranslation()
  const queryClient = useQueryClient()
  const form = useForm<DetailsValues>({
    resolver: zodResolver(detailsSchema),
    defaultValues: { full_name: me.full_name, locale: me.locale },
  })
  const save = useMutation({
    mutationFn: (values: DetailsValues) => call(api.PATCH('/api/v1/me', { body: values })),
    onSuccess: async (updated) => {
      queryClient.setQueryData(ME_QUERY_KEY, updated)
      storeLocale(updated.locale)
      await i18n.changeLanguage(updated.locale)
    },
    onError: (error) => applyServerErrors(error, form.setError, ['full_name', 'locale']),
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('details.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void form.handleSubmit((values) => {
              save.mutate(values)
            })(event)
          }}
        >
          <FormMessage success={save.isSuccess ? tc('states.saved') : null} />
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">{t('details.email')}</dt>
            <dd>{me.email}</dd>
            <dt className="text-muted-foreground">{t('details.role')}</dt>
            <dd>{tc(`roles.${me.role}`)}</dd>
          </dl>
          <FormField
            label={t('details.fullName')}
            required
            error={form.formState.errors.full_name?.message}
          >
            {(control) => (
              <Input {...control} autoComplete="name" {...form.register('full_name')} />
            )}
          </FormField>
          <FormField label={t('details.language')}>
            {(control) => (
              <NativeSelect {...control} {...form.register('locale')}>
                {SUPPORTED_LOCALES.map((locale) => (
                  <option key={locale} value={locale}>
                    {tc(`language.${locale}`)}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <Button type="submit" className="self-start" disabled={save.isPending}>
            {save.isPending ? tc('actions.saving') : tc('actions.save')}
          </Button>
          <UnsavedChangesGuard
            when={
              form.formState.isDirty &&
              !form.formState.isSubmitting &&
              !form.formState.isSubmitSuccessful
            }
          />
        </form>
      </CardContent>
    </Card>
  )
}

const passwordSchema = z
  .object({
    current_password: z.string().min(1, { error: 'validation.required' }),
    new_password: z
      .string()
      .min(12, { error: 'password.too_short' })
      .max(128, { error: 'password.too_long' }),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, {
    path: ['confirm'],
    error: 'validation.passwords_mismatch',
  })
type PasswordValues = z.infer<typeof passwordSchema>

function PasswordCard() {
  const { t } = useTranslation('profile')
  const queryClient = useQueryClient()
  const [formError, setFormError] = useState<string | null>(null)
  const form = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: '', new_password: '', confirm: '' },
  })
  const change = useMutation({
    mutationFn: (values: PasswordValues) =>
      call(
        api.POST('/api/v1/auth/password/change', {
          body: { current_password: values.current_password, new_password: values.new_password },
        }),
      ),
    onSuccess: async () => {
      setFormError(null)
      form.reset()
      await queryClient.invalidateQueries({ queryKey: SESSIONS_KEY })
    },
    onError: (error) => {
      setFormError(applyServerErrors(error, form.setError, ['current_password', 'new_password']))
    },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('password.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void form.handleSubmit((values) => {
              change.mutate(values)
            })(event)
          }}
        >
          <FormMessage error={formError} success={change.isSuccess ? t('password.done') : null} />
          <FormField
            label={t('password.current')}
            required
            error={form.formState.errors.current_password?.message}
          >
            {(control) => (
              <Input
                {...control}
                type="password"
                autoComplete="current-password"
                {...form.register('current_password')}
              />
            )}
          </FormField>
          <FormField
            label={t('password.new')}
            required
            error={form.formState.errors.new_password?.message}
          >
            {(control) => (
              <Input
                {...control}
                type="password"
                autoComplete="new-password"
                {...form.register('new_password')}
              />
            )}
          </FormField>
          <FormField
            label={t('password.confirm')}
            required
            error={form.formState.errors.confirm?.message}
          >
            {(control) => (
              <Input
                {...control}
                type="password"
                autoComplete="new-password"
                {...form.register('confirm')}
              />
            )}
          </FormField>
          <Button type="submit" className="self-start" disabled={change.isPending}>
            {t('password.submit')}
          </Button>
          <UnsavedChangesGuard
            when={
              form.formState.isDirty &&
              !form.formState.isSubmitting &&
              !form.formState.isSubmitSuccessful
            }
          />
        </form>
      </CardContent>
    </Card>
  )
}

const SESSIONS_KEY = ['me', 'sessions'] as const

function SessionsCard() {
  const { t } = useTranslation('profile')
  const locale = useLocale()
  const queryClient = useQueryClient()
  const notify = useNotify()
  const sessions = useQuery({
    queryKey: SESSIONS_KEY,
    queryFn: () => call(api.GET('/api/v1/me/sessions')),
  })
  const revoke = useMutation({
    mutationFn: (sessionId: string) =>
      call(
        api.DELETE('/api/v1/me/sessions/{session_id}', {
          params: { path: { session_id: sessionId } },
        }),
      ),
    onSuccess: async () => {
      notify.success(t('sessions.revoked'))
      await queryClient.invalidateQueries({ queryKey: SESSIONS_KEY })
    },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('sessions.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        <FormMessage error={revoke.error instanceof ApiError ? revoke.error.code : null} />
        {sessions.data ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('sessions.device')}</TableHead>
                <TableHead>{t('sessions.ip')}</TableHead>
                <TableHead className="hidden lg:table-cell">{t('sessions.started')}</TableHead>
                <TableHead>{t('sessions.lastSeen')}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sessions.data.map((session) => (
                <TableRow key={session.id}>
                  <TableCell className="max-w-64 truncate" title={session.user_agent ?? ''}>
                    {session.user_agent ?? t('sessions.unknownDevice')}
                  </TableCell>
                  <TableCell>{session.ip ?? ''}</TableCell>
                  <TableCell className="hidden lg:table-cell">
                    {formatDateTime(session.created_at, locale)}
                  </TableCell>
                  <TableCell>{formatDateTime(session.last_seen_at, locale)}</TableCell>
                  <TableCell className="text-right">
                    {session.current ? (
                      <Badge variant="secondary">{t('sessions.current')}</Badge>
                    ) : (
                      <ConfirmButton
                        label={t('sessions.revoke')}
                        title={t('sessions.revokeTitle')}
                        description={t('sessions.revokeDescription')}
                        size="sm"
                        variant="destructive"
                        disabled={revoke.isPending}
                        onConfirm={() => {
                          revoke.mutate(session.id)
                        }}
                      />
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Loading variant="table" />
        )}
      </CardContent>
    </Card>
  )
}
