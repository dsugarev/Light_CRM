import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'

import { api, call, type Schemas } from '@/api/client'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { useSectionCrumbs } from '@/components/useSectionCrumbs'
import { Card, CardContent } from '@/components/ui/card'
import { useNotify } from '@/lib/notify'

import { OrganizationForm } from './OrganizationForm'
import { organizationPayload, type OrganizationValues } from './organizationValues'

function useAfterSave() {
  const notify = useNotify()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  return async (org: Schemas['OrganizationOut'], message: string) => {
    await queryClient.invalidateQueries({ queryKey: ['organizations'] })
    notify.success(message)
    for (const warning of org.warnings) notify.warning(warning.code)
    await navigate(`/organizations/${org.id}`)
  }
}

export function OrganizationNewPage() {
  const { t } = useTranslation('party')
  const crumbs = useSectionCrumbs()
  const afterSave = useAfterSave()
  const create = useMutation({
    mutationFn: ({ values, confirm }: { values: OrganizationValues; confirm: boolean }) =>
      call(
        api.POST('/api/v1/organizations', {
          body: { ...organizationPayload(values), confirm_duplicate: confirm },
        }),
      ),
    onSuccess: (org) => afterSave(org, t('organization.toasts.created')),
  })
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader title={t('organization.createTitle')} breadcrumbs={[crumbs.organizations]} />
      <Card>
        <CardContent>
          <OrganizationForm
            submitLabel={t('organization.create')}
            pending={create.isPending}
            onSubmit={(values, confirm) => create.mutateAsync({ values, confirm })}
          />
        </CardContent>
      </Card>
    </section>
  )
}

export function OrganizationEditPage() {
  const { orgId = '' } = useParams()
  const { t } = useTranslation('party')
  const crumbs = useSectionCrumbs()
  const { t: tc } = useTranslation()
  const afterSave = useAfterSave()
  const path = { params: { path: { org_id: orgId } } }
  const organization = useQuery({
    queryKey: ['organizations', orgId],
    queryFn: () => call(api.GET('/api/v1/organizations/{org_id}', path)),
  })
  const save = useMutation({
    mutationFn: ({ values, confirm }: { values: OrganizationValues; confirm: boolean }) =>
      call(
        api.PATCH('/api/v1/organizations/{org_id}', {
          ...path,
          body: { ...organizationPayload(values), confirm_duplicate: confirm },
        }),
      ),
    onSuccess: (org) => afterSave(org, t('organization.toasts.saved')),
  })
  if (organization.isError)
    return (
      <ErrorState
        error={organization.error}
        onRetry={() => {
          void organization.refetch()
        }}
      />
    )
  if (!organization.data) return <Loading variant="form" />
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader
        title={t('organization.editTitle')}
        breadcrumbs={[
          crumbs.organizations,
          { label: organization.data.name, to: `/organizations/${orgId}` },
        ]}
      />
      <Card>
        <CardContent>
          <OrganizationForm
            organization={organization.data}
            submitLabel={tc('actions.save')}
            pending={save.isPending}
            onSubmit={(values, confirm) => save.mutateAsync({ values, confirm })}
          />
        </CardContent>
      </Card>
    </section>
  )
}
