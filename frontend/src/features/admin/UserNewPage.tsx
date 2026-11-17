import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { api, call } from '@/api/client'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useLocale } from '@/lib/useLocale'

import { PasswordLinkPanel } from './PasswordLinkPanel'
import { UserForm, type UserValues } from './UserForm'

/** FR-AUTH-02: no self-registration; the Admin creates the user and hands over a link. */
export function UserNewPage() {
  const { t } = useTranslation('admin')
  const locale = useLocale()
  const queryClient = useQueryClient()
  const create = useMutation({
    mutationFn: (values: UserValues) => call(api.POST('/api/v1/users', { body: values })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  return (
    <section className="mx-auto max-w-xl">
      <PageHeader title={t('userForm.createTitle')} />
      <Card>
        <CardContent className="flex flex-col gap-4">
          {create.data ? (
            <>
              <PasswordLinkPanel
                link={create.data.set_password}
                name={create.data.user.full_name}
              />
              <Button
                render={<Link to={`/admin/users/${create.data.user.id}`} />}
                nativeButton={false}
                className="self-start"
              >
                {t('link.openUser')}
              </Button>
            </>
          ) : (
            <UserForm
              defaultValues={{ email: '', full_name: '', role: 'sales_rep', locale }}
              submitLabel={t('userForm.create')}
              pending={create.isPending}
              onSubmit={(values) => create.mutateAsync(values)}
            />
          )}
        </CardContent>
      </Card>
    </section>
  )
}
