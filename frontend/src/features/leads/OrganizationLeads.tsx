import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { api, asPage, call } from '@/api/client'
import { DataTable, type Column } from '@/components/DataTable'
import { Loading } from '@/components/Loading'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatMoney } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { LeadStatusBadge } from './LeadStatusBadge'
import type { Lead } from './leadValues'

/** Leads section of the organization 360 page (FR-PARTY-03). */
export function OrganizationLeads({
  organizationId,
  canCreate,
}: {
  organizationId: string
  canCreate: boolean
}) {
  const { t } = useTranslation('leads')
  const locale = useLocale()
  const leads = useQuery({
    queryKey: ['organizations', organizationId, 'leads'],
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/organizations/{org_id}/leads', {
            params: { path: { org_id: organizationId }, query: { page_size: 100 } },
          }),
        ),
      ),
  })
  const columns: Column<Lead>[] = [
    {
      key: 'title',
      header: t('list.columns.title'),
      cell: (lead) => (
        <Link to={`/leads/${lead.id}`} className="font-medium hover:underline">
          {lead.title}
        </Link>
      ),
    },
    {
      key: 'status',
      header: t('list.columns.status'),
      cell: (lead) => <LeadStatusBadge status={lead.status} />,
    },
    { key: 'score', header: t('list.columns.score'), cell: (lead) => lead.qualification.score },
    {
      key: 'value',
      header: t('list.columns.value'),
      cell: (lead) => (lead.estimated_value ? formatMoney(lead.estimated_value, locale) : ''),
    },
  ]
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t('organization.title')}</CardTitle>
        {canCreate ? (
          <Link
            to={`/leads/new?organization_id=${organizationId}`}
            className={buttonVariants({ variant: 'outline', size: 'sm' })}
          >
            {t('organization.new')}
          </Link>
        ) : null}
      </CardHeader>
      <CardContent>
        {leads.data ? (
          <DataTable
            columns={columns}
            rows={leads.data.items}
            rowKey={(lead) => lead.id}
            sort="-created_at"
            onSort={() => undefined}
            empty={t('organization.none')}
          />
        ) : (
          <Loading variant="table" />
        )}
      </CardContent>
    </Card>
  )
}
