import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, call, type Schemas } from '@/api/client'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import type { RowAction } from '@/components/RowActions'
import { Button } from '@/components/ui/button'
import { Sheet } from '@/components/ui/sheet'
import { useMe } from '@/features/auth/useMe'
import { useNotify } from '@/lib/notify'

import { PasswordLinkPanel } from './PasswordLinkPanel'

type User = Schemas['UserOut']
type Action = 'unlock' | 'deactivate' | 'activate' | 'reset' | 'revoke'

const DONE: Partial<Record<Action, 'unlocked' | 'deactivated' | 'activated' | 'revoked'>> = {
  unlock: 'unlocked',
  deactivate: 'deactivated',
  activate: 'activated',
  revoke: 'revoked',
}

/**
 * FN-03: the account actions of the user list's row menu (API spec section 5), each
 * confirmed first. A reset link is shown once in a sheet, like a new user's link (UX-09),
 * and forgotten when the sheet closes.
 */
export function useUserActions() {
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const notify = useNotify()
  const queryClient = useQueryClient()
  const { data: me } = useMe()
  const [confirming, setConfirming] = useState<{ action: Action; user: User } | null>(null)
  const [shown, setShown] = useState<{ link: Schemas['PasswordLink']; name: string } | null>(null)

  const run = useMutation({
    mutationFn: ({ action, user }: { action: Action; user: User }): Promise<unknown> => {
      const path = { params: { path: { user_id: user.id } } }
      switch (action) {
        case 'unlock':
          return call(api.POST('/api/v1/users/{user_id}/unlock', path))
        case 'deactivate':
          return call(api.POST('/api/v1/users/{user_id}/deactivate', path))
        case 'activate':
          return call(api.POST('/api/v1/users/{user_id}/activate', path))
        case 'reset':
          return call(api.POST('/api/v1/users/{user_id}/password-reset', path))
        case 'revoke':
          return call(api.DELETE('/api/v1/users/{user_id}/sessions', path))
      }
    },
    // The reset link is not kept in the mutation cache once it is no longer shown.
    gcTime: 0,
    onSuccess: async (result, { action, user }) => {
      const done = DONE[action]
      if (done) notify.success(t(`userDetail.done.${done}`))
      if (action === 'reset') {
        setShown({ link: result as Schemas['PasswordLink'], name: user.full_name })
      }
      await queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (error) => {
      notify.error(error)
    },
  })

  const ask = (action: Action, user: User) => () => {
    setConfirming({ action, user })
  }
  const menuFor = (user: User): RowAction[] => [
    ...(user.is_locked && user.is_active
      ? [{ label: t('userDetail.unlock'), onSelect: ask('unlock', user) }]
      : []),
    ...(user.is_active
      ? [
          { label: t('userDetail.resetPassword'), onSelect: ask('reset', user) },
          { label: t('userDetail.revokeSessions'), onSelect: ask('revoke', user) },
          // Not on yourself: an Admin cannot lock themselves out from the list.
          ...(user.id === me?.id
            ? []
            : [{ label: t('userDetail.deactivate'), onSelect: ask('deactivate', user) }]),
        ]
      : [{ label: t('userDetail.activate'), onSelect: ask('activate', user) }]),
  ]

  const texts: Record<Action, [string, string]> = {
    unlock: ['userDetail.unlock', 'userDetail.confirmUnlock'],
    deactivate: ['userDetail.deactivate', 'userDetail.confirmDeactivate'],
    activate: ['userDetail.activate', 'userDetail.confirmActivate'],
    reset: ['userDetail.resetPassword', 'userDetail.confirmReset'],
    revoke: ['userDetail.revokeSessions', 'userDetail.confirmRevoke'],
  }
  const closeLink = () => {
    setShown(null)
    run.reset()
  }

  const dialogs = (
    <>
      <ConfirmDialog
        open={confirming !== null}
        title={confirming ? t(texts[confirming.action][0] as 'userDetail.unlock') : ''}
        description={
          confirming
            ? t(texts[confirming.action][1] as 'userDetail.confirmUnlock', {
                name: confirming.user.full_name,
              })
            : ''
        }
        confirmLabel={
          confirming ? t(texts[confirming.action][0] as 'userDetail.unlock') : undefined
        }
        variant={confirming?.action === 'deactivate' ? 'destructive' : 'default'}
        onCancel={() => {
          setConfirming(null)
        }}
        onConfirm={() => {
          if (confirming) run.mutate(confirming)
          setConfirming(null)
        }}
      />
      <Sheet
        open={shown !== null}
        onOpenChange={(open) => {
          if (!open) closeLink()
        }}
        title={t('userDetail.resetTitle')}
        closeLabel={tc('actions.close')}
      >
        {shown ? (
          <div className="flex flex-col gap-4">
            <PasswordLinkPanel link={shown.link} name={shown.name} />
            <p className="text-sm font-medium">{t('link.onlyOnce')}</p>
            <Button type="button" className="self-start" onClick={closeLink}>
              {tc('actions.done')}
            </Button>
          </div>
        ) : null}
      </Sheet>
    </>
  )
  return { menuFor, dialogs, pending: run.isPending }
}
