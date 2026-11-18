import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { api, ApiError, asPage, call, type Schemas } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { DataTable, type Column } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { useSectionCrumbs } from '@/components/useSectionCrumbs'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useCanEditOwned } from '@/features/auth/useOwnership'
import { RecordTimeline } from '@/features/activities/RecordTimeline'
import { ExternalReferences } from '@/features/integrations/ExternalReferences'
import { OrganizationLeads } from '@/features/leads/OrganizationLeads'
import { OrganizationOpportunities } from '@/features/opportunities/OrganizationOpportunities'
import { referenceName } from '@/features/reference/useReferenceList'
import { useErrorText } from '@/lib/errors'
import { formatDate, formatMoney, formatNumber } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useLocale } from '@/lib/useLocale'
import { useNotify } from '@/lib/notify'

type Contact = Schemas['ContactOut']

/** FR-PARTY-03: the organization with its contacts; leads, opportunities and the
 * timeline fill in as Phases 3 and 4 add them. */
export function OrganizationPage() {
  const notify = useNotify()
  const { orgId = '' } = useParams()
  const { t } = useTranslation('party')
  const crumbs = useSectionCrumbs()
  const locale = useLocale()
  const can = useCan()
  const canEdit = useCanEditOwned()
  const errorText = useErrorText()
  const queryClient = useQueryClient()
  const path = { params: { path: { org_id: orgId } } }
  const organization = useQuery({
    queryKey: ['organizations', orgId],
    queryFn: () => call(api.GET('/api/v1/organizations/{org_id}', path)),
  })
  const contacts = useQuery({
    queryKey: ['organizations', orgId, 'contacts'],
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/organizations/{org_id}/contacts', {
            params: { path: { org_id: orgId }, query: { page_size: 100 } },
          }),
        ),
      ),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['organizations'] })
  const archive = useMutation({
    mutationFn: () => call(api.DELETE('/api/v1/organizations/{org_id}', path)),
    onSuccess: async () => {
      await refresh()
      notify.success(t('organization.toasts.archived'))
    },
  })
  const restore = useMutation({
    mutationFn: () => call(api.POST('/api/v1/organizations/{org_id}/restore', path)),
    onSuccess: async () => {
      await refresh()
      notify.success(t('organization.toasts.restored'))
    },
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
  if (!organization.data) return <Loading />
  const org = organization.data
  const editable = canEdit(org.owner.id)
  const actionError = [archive.error, restore.error].find((e) => e instanceof ApiError)
  const canAddContact = can('records.create') && !org.archived_at

  const details: [string, string | null | undefined][] = [
    [t('organization.fields.registrationNumber'), org.registration_number],
    [t('organization.fields.vatNumber'), org.vat_number],
    [t('organization.fields.industry'), org.industry ? referenceName(org.industry, locale) : null],
    [
      t('organization.fields.sizeBand'),
      org.size_band ? t(`organization.sizeBands.${org.size_band}`) : null,
    ],
    [t('organization.fields.website'), org.website],
    [
      t('organization.fields.addressLine'),
      [org.address_line, org.postal_code, org.city, org.country].filter(Boolean).join(', '),
    ],
    [t('organization.fields.owner'), org.owner.full_name],
  ]
  const contactColumns: Column<Contact>[] = [
    {
      key: 'name',
      header: t('contacts.columns.name'),
      cell: (c) => (
        <Link to={`/contacts/${c.id}`} className="font-medium hover:underline">
          {c.full_name}
        </Link>
      ),
    },
    { key: 'job', header: t('contacts.columns.jobTitle'), cell: (c) => c.job_title ?? '' },
    { key: 'email', header: t('contacts.columns.email'), cell: (c) => c.email ?? '' },
    { key: 'phone', header: t('contacts.columns.phone'), cell: (c) => c.phone ?? '' },
  ]

  return (
    <section className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title={org.name}
        breadcrumbs={[crumbs.organizations]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {org.archived_at ? (
              <Badge variant="outline">
                {t('organization.detail.archivedOn', { date: formatDate(org.archived_at, locale) })}
              </Badge>
            ) : null}
            {editable && !org.archived_at ? (
              <Link
                to={`/organizations/${org.id}/edit`}
                className={buttonVariants({ variant: 'outline' })}
              >
                {t('organization.detail.edit')}
              </Link>
            ) : null}
            {editable && !org.archived_at ? (
              <ConfirmButton
                label={t('organization.detail.archive')}
                title={t('organization.detail.archive')}
                description={t('organization.detail.confirmArchive', { name: org.name })}
                variant="destructive"
                disabled={archive.isPending}
                onConfirm={() => {
                  archive.mutate()
                }}
              />
            ) : null}
            {org.archived_at && can('records.restore') ? (
              <Button
                type="button"
                variant="outline"
                disabled={restore.isPending}
                onClick={() => {
                  restore.mutate()
                }}
              >
                {t('organization.detail.restore')}
              </Button>
            ) : null}
          </div>
        }
      />
      <FormMessage error={actionError instanceof ApiError ? actionError.code : null} />
      {org.warnings.map((w) => (
        <Alert key={w.code}>
          <AlertDescription>{errorText(w.code)}</AlertDescription>
        </Alert>
      ))}
      <dl className="grid gap-3 sm:grid-cols-4" aria-label={t('organization.detail.details')}>
        {(
          [
            [t('organization.detail.counts.contacts'), formatNumber(org.counts.contacts, locale)],
            [
              t('organization.detail.counts.openLeads'),
              formatNumber(org.counts.open_leads, locale),
            ],
            [
              t('organization.detail.counts.openOpportunities'),
              formatNumber(org.counts.open_opportunities, locale),
            ],
            [
              t('organization.detail.counts.pipelineValue'),
              formatMoney(org.counts.open_pipeline_value, locale),
            ],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="rounded-lg border p-3">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="text-lg font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        <Card>
          <CardHeader>
            <CardTitle>{t('organization.detail.details')}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
              {details.map(([label, value]) => (
                <div key={label} className="contents">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd>
                    {value === null || value === undefined || value === ''
                      ? t('organization.none')
                      : value}
                  </dd>
                </div>
              ))}
            </dl>
            {org.notes ? <p className="mt-4 whitespace-pre-wrap text-sm">{org.notes}</p> : null}
          </CardContent>
        </Card>
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>{t('organization.detail.contacts')}</CardTitle>
              {canAddContact ? (
                <Link
                  to={`/contacts/new?organization_id=${org.id}`}
                  className={buttonVariants({ variant: 'outline', size: 'sm' })}
                >
                  {t('organization.detail.addContact')}
                </Link>
              ) : null}
            </CardHeader>
            <CardContent>
              {contacts.data ? (
                <DataTable
                  columns={contactColumns}
                  rows={contacts.data.items}
                  rowKey={(c) => c.id}
                  sort="last_name"
                  onSort={() => undefined}
                />
              ) : (
                <Loading variant="table" />
              )}
            </CardContent>
          </Card>
          <OrganizationLeads organizationId={org.id} canCreate={canAddContact} />
          <OrganizationOpportunities organizationId={org.id} canCreate={canAddContact} />
          <ExternalReferences resource="organizations" id={org.id} />
          <RecordTimeline record={{ kind: 'organization', id: org.id }} canLog={!org.archived_at} />
        </div>
      </div>
    </section>
  )
}
