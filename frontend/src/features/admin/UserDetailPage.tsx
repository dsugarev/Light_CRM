import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'

import { api, ApiError, call, type Schemas } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { FormMessage } from '@/components/FormMessage'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { useSectionCrumbs } from '@/components/useSectionCrumbs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useMe } from '@/features/auth/useMe'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { PasswordLinkPanel } from './PasswordLinkPanel'
import { useLastAdmin } from './useLastAdmin'
import { UserStatus } from './UsersPage'
import { EditUserSheet } from './UserSheets'

type User = Schemas['UserOut']
type Action = 'deactivate' | 'activate' | 'unlock'

export function UserDetailPage() {
  const { userId = '' } = useParams()
  const { t } = useTranslation('admin')
  const crumbs = useSectionCrumbs()
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const { data: me } = useMe()
  const queryClient = useQueryClient()
  const isLastAdmin = useLastAdmin()
  const { t: te } = useTranslation('errors')
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

  const [editing, setEditing] = useState(false)
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
    // UX-09: the one-time link is not kept in the mutation cache once the page is left.
    gcTime: 0,
  })
  const revoke = useMutation({
    mutationFn: () => call(api.DELETE('/api/v1/users/{user_id}/sessions', path)),
    onSuccess: () => {
      setMessage(t('userDetail.done.revoked'))
    },
  })

  if (user.isError) return <ErrorState error={user.error} />
  if (!user.data) return <Loading />
  const u = user.data
  const isSelf = me?.id === u.id
  // FN-08: say why Deactivate is not available.
  const lastAdmin = isLastAdmin(u)
  const deactivateBlocked = lastAdmin
    ? te('permission.last_admin')
    : isSelf
      ? t('userDetail.notSelf')
      : null
  const actionError = [act.error, reset.error, revoke.error].find((e) => e instanceof ApiError)

  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        title={u.full_name}
        breadcrumbs={[crumbs.users]}
        actions={
          <div className="flex items-center gap-2">
            <UserStatus user={u} />
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setEditing(true)
              }}
            >
              {tc('actions.edit')}
            </Button>
          </div>
        }
      />
      <EditUserSheet
        user={editing ? u : null}
        onClose={() => {
          setEditing(false)
        }}
      />
      <FormMessage
        error={actionError instanceof ApiError ? actionError.code : null}
        success={message}
      />
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
          {u.is_active && deactivateBlocked ? (
            <p className="text-sm text-muted-foreground">{deactivateBlocked}</p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {u.is_active ? (
              <ConfirmButton
                label={t('userDetail.deactivate')}
                title={t('userDetail.deactivate')}
                description={t('userDetail.confirmDeactivate', { name: u.full_name })}
                variant="destructive"
                disabled={isSelf || lastAdmin || act.isPending}
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
