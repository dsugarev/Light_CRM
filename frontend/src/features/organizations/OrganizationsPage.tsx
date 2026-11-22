import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { api, asPage, call, type Schemas } from '@/api/client'
import { ListEmptyState } from '@/components/ListEmptyState'
import { DataTable, type Column } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { FilterBar } from '@/components/FilterBar'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { SearchInput } from '@/components/SearchInput'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import { referenceName, useReferenceList } from '@/features/reference/useReferenceList'
import { formatDateTime } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useListParams } from '@/lib/useListParams'
import { useLocale } from '@/lib/useLocale'
import { ExportMenu } from '@/features/reports/ExportMenu'

type Organization = Schemas['OrganizationOut']
const PAGE_SIZE = 25

/** FR-PARTY-04: list, search and filter; every filter is kept in the URL. */
export function OrganizationsPage() {
  const { t } = useTranslation('party')
  const locale = useLocale()
  const can = useCan()
  const list = useListParams({ sort: 'name', filters: ['owner_id', 'industry_id'] as const })
  const industries = useReferenceList('industries')

  const organizations = useQuery({
    queryKey: ['organizations', list.key],
    // Keep showing the current rows while the next page, sort or filter loads.
    placeholderData: keepPreviousData,
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/organizations', {
            params: { query: { ...list.apiQuery, page_size: PAGE_SIZE } },
          }),
        ),
      ),
  })

  const columns: Column<Organization>[] = [
    {
      key: 'name',
      header: t('organizations.columns.name'),
      sortKey: 'name',
      cell: (org) => (
        <span className="flex items-center gap-2">
          <Link to={`/organizations/${org.id}`} className="font-medium hover:underline">
            {org.name}
          </Link>
          {org.archived_at ? <Badge variant="outline">{t('organizations.archived')}</Badge> : null}
        </span>
      ),
    },
    { key: 'city', header: t('organizations.columns.city'), cell: (org) => org.city ?? '' },
    {
      key: 'industry',
      header: t('organizations.columns.industry'),
      cell: (org) => (org.industry ? referenceName(org.industry, locale) : ''),
    },
    { key: 'owner', header: t('organizations.columns.owner'), cell: (org) => org.owner.full_name },
    {
      key: 'updated',
      header: t('organizations.columns.updated'),
      sortKey: 'updated_at',
      cell: (org) => formatDateTime(org.updated_at, locale),
    },
  ]

  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader
        title={t('organizations.title')}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ExportMenu path="/api/v1/organizations/export" query={list.apiQuery} />
            {can('records.create') ? (
              <Link to="/organizations/new" className={buttonVariants()}>
                {t('organizations.new')}
              </Link>
            ) : null}
          </div>
        }
      />
      <FilterBar>
        <SearchInput
          label={t('organizations.search')}
          value={list.q}
          onChange={(q) => {
            list.update({ q })
          }}
        />
        <NativeSelect
          aria-label={t('organizations.filters.owner')}
          value={list.filters.owner_id[0] ?? ''}
          onChange={(e) => {
            list.update({ owner_id: e.target.value || null })
          }}
        >
          <option value="">{t('organizations.filters.everyone')}</option>
          <option value="me">{t('organizations.filters.mine')}</option>
        </NativeSelect>
        <NativeSelect
          aria-label={t('organizations.filters.industry')}
          value={list.filters.industry_id[0] ?? ''}
          onChange={(e) => {
            list.update({ industry_id: e.target.value || null })
          }}
        >
          <option value="">{t('organizations.filters.allIndustries')}</option>
          {(industries.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {referenceName(item, locale)}
            </option>
          ))}
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={list.archived}
            onChange={(e) => {
              list.update({ archived: e.target.checked ? '1' : null })
            }}
          />
          {t('organizations.filters.archived')}
        </label>
      </FilterBar>
      {organizations.isError ? (
        <ErrorState
          error={organizations.error}
          onRetry={() => {
            void organizations.refetch()
          }}
        />
      ) : null}
      {organizations.data ? (
        <>
          <DataTable
            busy={organizations.isPlaceholderData}
            caption={t('organizations.title')}
            columns={columns}
            rows={organizations.data.items}
            rowKey={(org) => org.id}
            sort={list.sort}
            onSort={(sort) => {
              list.update({ sort })
            }}
            empty={
              <ListEmptyState
                filtered={list.filtered}
                onClear={list.clear}
                create={
                  can('records.create')
                    ? { to: '/organizations/new', label: t('organizations.new') }
                    : undefined
                }
              />
            }
          />
          <Pagination
            page={list.page}
            pageSize={PAGE_SIZE}
            total={organizations.data.total}
            onPageChange={(page) => {
              list.update({ page: String(page) })
            }}
          />
        </>
      ) : organizations.isPending ? (
        <Loading variant="table" />
      ) : null}
    </section>
  )
}
