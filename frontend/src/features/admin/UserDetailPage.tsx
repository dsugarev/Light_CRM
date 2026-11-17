import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'

import { api, ApiError, call, type Schemas } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useMe } from '@/features/auth/useMe'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { PasswordLinkPanel } from './PasswordLinkPanel'
import { UserForm, type UserValues } from './UserForm'
import { UserStatus } from './UsersPage'

type User = Schemas['UserOut']
type Action = 'deactivate' | 'activate' | 'unlock'

export function UserDetailPage() {
  const { userId = '' } = useParams()
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const { data: me } = useMe()
  const queryClient = useQueryClient()
  const [message, setMessage] = useState<string | null>(null)
  const path = { params: { path: { user_id: userId } } }
  const key = ['users', userId]

  const user = useQuery({
    queryKey: key,
    queryFn: () => call(api.GET('/api/v1/users/{user_id}', path)),
  })
  const refresh = (updated: User) => {
    queryClient.setQueryData(key, updated)
    void queryClient.invalidateQueries({ queryKey: ['users'], exact: false })
  }

  const save = useMutation({
    mutationFn: (values: UserValues) =>
      call(api.PATCH('/api/v1/users/{user_id}', { ...path, body: values })),
    onSuccess: (updated) => {
      refresh(updated)
      setMessage(tc('states.saved'))
    },
  })
  const act = useMutation({
    mutationFn: (action: Action) => {
      switch (action) {
        case 'deactivate':
          return call(api.POST('/api/v1/users/{user_id}/deactivate', path))
        case 'activate':
          return call(api.POST('/api/v1/users/{user_id}/activate', path))
        case 'unlock':
          return call(api.POST('/api/v1/users/{user_id}/unlock', path))
      }
    },
    onSuccess: (updated, action) => {
      refresh(updated)
      const done = { deactivate: 'deactivated', activate: 'activated', unlock: 'unlocked' } as const
      setMessage(t(`userDetail.done.${done[action]}`))
    },
  })
  const reset = useMutation({
    mutationFn: () => call(api.POST('/api/v1/users/{user_id}/password-reset', path)),
  })
  const revoke = useMutation({
    mutationFn: () => call(api.DELETE('/api/v1/users/{user_id}/sessions', path)),
    onSuccess: () => {
      setMessage(t('userDetail.done.revoked'))
    },
  })

  if (!user.data) return user.isError ? <FormMessage error="resource.not_found" /> : <Loading />
  const u = user.data
  const isSelf = me?.id === u.id
  const actionError = [act.error, reset.error, revoke.error].find((e) => e instanceof ApiError)

  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader title={u.full_name} actions={<UserStatus user={u} />} />
      <FormMessage
        error={actionError instanceof ApiError ? actionError.code : null}
        success={message}
      />
      <Card>
        <CardHeader>
          <CardTitle>{t('userForm.editTitle')}</CardTitle>
        </CardHeader>
        <CardContent>
          <UserForm
            key={u.updated_at}
            defaultValues={{
              email: u.email,
              full_name: u.full_name,
              role: u.role as UserValues['role'],
              locale: u.locale,
            }}
            submitLabel={t('userForm.editTitle')}
            pending={save.isPending}
            onSubmit={(values) => save.mutateAsync(values)}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t('userDetail.actions')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">{t('userDetail.created')}</dt>
            <dd>{formatDateTime(u.created_at, locale)}</dd>
            <dt className="text-muted-foreground">{t('userDetail.lastLogin')}</dt>
            <dd>{u.last_login_at ? formatDateTime(u.last_login_at, locale) : t('users.never')}</dd>
            {u.locked_until ? (
              <>
                <dt className="text-muted-foreground">{t('userDetail.status')}</dt>
                <dd>
                  {t('userDetail.lockedUntil', { time: formatDateTime(u.locked_until, locale) })}
                </dd>
              </>
            ) : null}
          </dl>
          <div className="flex flex-wrap gap-2">
            {u.is_active ? (
              <ConfirmButton
                label={t('userDetail.deactivate')}
                title={t('userDetail.deactivate')}
                description={t('userDetail.confirmDeactivate', { name: u.full_name })}
                variant="destructive"
                disabled={isSelf || act.isPending}
                onConfirm={() => {
                  act.mutate('deactivate')
                }}
              />
            ) : (
              <Button
                type="button"
                variant="outline"
                disabled={act.isPending}
                onClick={() => {
                  act.mutate('activate')
                }}
              >
                {t('userDetail.activate')}
              </Button>
            )}
            {u.is_locked ? (
              <Button
                type="button"
                variant="outline"
                disabled={act.isPending}
                onClick={() => {
                  act.mutate('unlock')
                }}
              >
                {t('userDetail.unlock')}
              </Button>
            ) : null}
            <Button
              type="button"
              variant="outline"
              disabled={!u.is_active || reset.isPending}
              onClick={() => {
                reset.mutate()
              }}
            >
              {t('userDetail.resetPassword')}
            </Button>
            <ConfirmButton
              label={t('userDetail.revokeSessions')}
              title={t('userDetail.revokeSessions')}
              description={t('userDetail.confirmRevoke', { name: u.full_name })}
              disabled={revoke.isPending}
              onConfirm={() => {
                revoke.mutate()
              }}
            />
          </div>
          {reset.data ? <PasswordLinkPanel link={reset.data} name={u.full_name} /> : null}
        </CardContent>
      </Card>
    </section>
  )
}
