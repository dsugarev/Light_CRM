import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { api, asPage, call } from '@/api/client'
import { DataTable, type Column } from '@/components/DataTable'
import { Loading } from '@/components/Loading'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDay, formatMoney } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import type { Opportunity } from './opportunityValues'
import { StageBadge } from './StageBadge'

/** Opportunities section of the organization 360 page (FR-PARTY-03). */
export function OrganizationOpportunities({
  organizationId,
  canCreate,
}: {
  organizationId: string
  canCreate: boolean
}) {
  const { t } = useTranslation('opportunities')
  const locale = useLocale()
  const opportunities = useQuery({
    queryKey: ['opportunities', 'organization', organizationId],
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/organizations/{org_id}/opportunities', {
            params: { path: { org_id: organizationId }, query: { page_size: 100 } },
          }),
        ),
      ),
  })
  const columns: Column<Opportunity>[] = [
    {
      key: 'name',
      header: t('list.columns.name'),
      cell: (o) => (
        <Link to={`/opportunities/${o.id}`} className="font-medium hover:underline">
          {o.name}
        </Link>
      ),
    },
    { key: 'stage', header: t('list.columns.stage'), cell: (o) => <StageBadge stage={o.stage} /> },
    {
      key: 'amount',
      header: t('list.columns.amount'),
      cell: (o) => (o.amount ? formatMoney(o.amount, locale) : ''),
    },
    {
      key: 'close',
      header: t('list.columns.expectedClose'),
      cell: (o) => (o.expected_close_date ? formatDay(o.expected_close_date, locale) : ''),
    },
  ]
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t('organization.title')}</CardTitle>
        {canCreate ? (
          <Link
            to={`/opportunities/new?organization_id=${organizationId}`}
            className={buttonVariants({ variant: 'outline', size: 'sm' })}
          >
            {t('organization.new')}
          </Link>
        ) : null}
      </CardHeader>
      <CardContent>
        {opportunities.data ? (
          <DataTable
            columns={columns}
            rows={opportunities.data.items}
            rowKey={(o) => o.id}
            sort="-updated_at"
            onSort={() => undefined}
            empty={t('organization.none')}
          />
        ) : (
          <Loading />
        )}
      </CardContent>
    </Card>
  )
}
