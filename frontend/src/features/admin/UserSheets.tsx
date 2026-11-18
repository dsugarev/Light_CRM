import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { api, call, type Schemas } from '@/api/client'
import { Button, buttonVariants } from '@/components/ui/button'
import { Sheet } from '@/components/ui/sheet'
import { useNotify } from '@/lib/notify'
import { useLocale } from '@/lib/useLocale'

import { PasswordLinkPanel } from './PasswordLinkPanel'
import { UserForm, type UserValues } from './UserForm'

type User = Schemas['UserOut']

/**
 * FR-AUTH-02, UX-09: create a user in a side sheet. The one-time link is shown once,
 * after creation. On close the mutation is reset and kept out of the mutation cache
 * (`gcTime: 0`), so the link is not held anywhere in the frontend afterwards.
 */
export function CreateUserSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const queryClient = useQueryClient()
  const create = useMutation({
    mutationFn: (values: UserValues) => call(api.POST('/api/v1/users', { body: values })),
    gcTime: 0,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })
  const close = () => {
    create.reset()
    onClose()
  }
  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) close()
      }}
      title={t('userForm.createTitle')}
      closeLabel={tc('actions.close')}
    >
      {create.data ? (
        <div className="flex flex-col gap-4">
          <PasswordLinkPanel link={create.data.set_password} name={create.data.user.full_name} />
          <p className="text-sm font-medium">{t('link.onlyOnce')}</p>
          <div className="flex flex-wrap gap-2">
            <Link
              to={`/admin/users/${create.data.user.id}`}
              className={buttonVariants({ variant: 'outline' })}
              onClick={() => {
                create.reset()
              }}
            >
              {t('link.openUser')}
            </Link>
            <Button type="button" onClick={close}>
              {tc('actions.done')}
            </Button>
          </div>
        </div>
      ) : (
        <UserForm
          defaultValues={{ email: '', full_name: '', role: 'sales_rep', locale }}
          submitLabel={t('userForm.create')}
          pending={create.isPending}
          onSubmit={(values) => create.mutateAsync(values)}
        />
      )}
    </Sheet>
  )
}

/** UX-09: edit a user's details in a side sheet, from the list or the user's page. */
export function EditUserSheet({ user, onClose }: { user: User | null; onClose: () => void }) {
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const notify = useNotify()
  const queryClient = useQueryClient()
  const save = useMutation({
    mutationFn: ({ id, values }: { id: string; values: UserValues }) =>
      call(
        api.PATCH('/api/v1/users/{user_id}', { params: { path: { user_id: id } }, body: values }),
      ),
    onSuccess: async (updated) => {
      queryClient.setQueryData(['users', updated.id], updated)
      await queryClient.invalidateQueries({ queryKey: ['users'] })
      notify.success(tc('states.saved'))
      onClose()
    },
  })
  return (
    <Sheet
      open={user !== null}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title={t('userForm.editTitle')}
      description={user?.full_name}
      closeLabel={tc('actions.close')}
    >
      {user ? (
        <UserForm
          key={user.id + user.updated_at}
          defaultValues={{
            email: user.email,
            full_name: user.full_name,
            role: user.role as UserValues['role'],
            locale: user.locale,
          }}
          submitLabel={tc('actions.save')}
          pending={save.isPending}
          onSubmit={(values) => save.mutateAsync({ id: user.id, values })}
        />
      ) : null}
    </Sheet>
  )
}
