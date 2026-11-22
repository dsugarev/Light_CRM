import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { api, asPage, call } from '@/api/client'
import { ListEmptyState } from '@/components/ListEmptyState'
import { DataTable, type Column } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { FilterBar } from '@/components/FilterBar'
import { PageHeader } from '@/components/PageHeader'
import { useSectionCrumbs } from '@/components/useSectionCrumbs'
import { Pagination } from '@/components/Pagination'
import { SearchInput } from '@/components/SearchInput'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { referenceName, useReferenceList } from '@/features/reference/useReferenceList'
import { formatDate, formatMoney } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useListParams } from '@/lib/useListParams'
import { useLocale } from '@/lib/useLocale'
import { ExportMenu } from '@/features/reports/ExportMenu'
import { useNotify } from '@/lib/notify'

import { LeadForm } from './LeadForm'
import { LeadStatusBadge } from './LeadStatusBadge'
import { LEAD_STATUSES, leadDefaults, leadPayload, type Lead, type LeadValues } from './leadValues'

const PAGE_SIZE = 25

/** FR-LEAD-05: sortable, filterable list; filters in the URL. */
export function LeadsPage() {
  const { t } = useTranslation('leads')
  const locale = useLocale()
  const can = useCan()
  const sources = useReferenceList('lead-sources')
  const list = useListParams({
    sort: '-created_at',
    filters: ['status', 'owner_id', 'source_id', 'fits_target_profile'] as const,
  })
  const leads = useQuery({
    queryKey: ['leads', list.key],
    placeholderData: keepPreviousData,
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/leads', {
            params: { query: { ...list.apiQuery, page_size: PAGE_SIZE } },
          }),
        ),
      ),
  })
  const columns: Column<Lead>[] = [
    {
      key: 'title',
      header: t('list.columns.title'),
      cell: (lead) => (
        <span className="flex items-center gap-2">
          <Link to={`/leads/${lead.id}`} className="font-medium hover:underline">
            {lead.title}
          </Link>
          {lead.archived_at ? <Badge variant="outline">{t('list.archived')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'company',
      header: t('list.columns.company'),
      sortKey: 'company_name',
      cell: (lead) => lead.company_name,
    },
    {
      key: 'status',
      header: t('list.columns.status'),
      cell: (lead) => <LeadStatusBadge status={lead.status} />,
    },
    {
      key: 'score',
      header: t('list.columns.score'),
      sortKey: 'qualification_score',
      cell: (lead) => lead.qualification.score,
      className: 'text-right hidden lg:table-cell',
    },
    {
      key: 'value',
      header: t('list.columns.value'),
      sortKey: 'estimated_value',
      cell: (lead) => (lead.estimated_value ? formatMoney(lead.estimated_value, locale) : ''),
      className: 'text-right',
    },
    {
      key: 'owner',
      className: 'hidden lg:table-cell',
      header: t('list.columns.owner'),
      cell: (lead) => lead.owner.full_name,
    },
    {
      key: 'created',
      className: 'hidden lg:table-cell',
      header: t('list.columns.created'),
      sortKey: 'created_at',
      cell: (lead) => formatDate(lead.created_at, locale),
    },
  ]
  return (
    <section className="mx-auto max-w-7xl">
      <PageHeader
        title={t('list.title')}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ExportMenu path="/api/v1/leads/export" query={list.apiQuery} />
            {can('records.create') ? (
              <Link to="/leads/new" className={buttonVariants()}>
                {t('list.new')}
              </Link>
            ) : null}
          </div>
        }
      />
      <FilterBar>
        <SearchInput
          label={t('list.search')}
          value={list.q}
          onChange={(q) => {
            list.update({ q })
          }}
        />
        <NativeSelect
          aria-label={t('list.status')}
          value={list.filters.status[0] ?? ''}
          onChange={(e) => {
            list.update({ status: e.target.value || null })
          }}
        >
          <option value="">{t('list.allStatuses')}</option>
          {LEAD_STATUSES.map((status) => (
            <option key={status} value={status}>
              {t(`status.${status}`)}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label={t('list.owner')}
          value={list.filters.owner_id[0] ?? ''}
          onChange={(e) => {
            list.update({ owner_id: e.target.value || null })
          }}
        >
          <option value="">{t('list.everyone')}</option>
          <option value="me">{t('list.mine')}</option>
        </NativeSelect>
        <NativeSelect
          aria-label={t('list.source')}
          value={list.filters.source_id[0] ?? ''}
          onChange={(e) => {
            list.update({ source_id: e.target.value || null })
          }}
        >
          <option value="">{t('list.allSources')}</option>
          {(sources.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {referenceName(item, locale)}
            </option>
          ))}
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={list.filters.fits_target_profile[0] === 'true'}
            onChange={(e) => {
              list.update({ fits_target_profile: e.target.checked ? 'true' : null })
            }}
          />
          {t('list.fit')}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={list.archived}
            onChange={(e) => {
              list.update({ archived: e.target.checked ? '1' : null })
            }}
          />
          {t('list.archived')}
        </label>
      </FilterBar>
      {leads.isError ? (
        <ErrorState
          error={leads.error}
          onRetry={() => {
            void leads.refetch()
          }}
        />
      ) : null}
      {leads.data ? (
        <>
          <DataTable
            caption={t('list.title')}
            columns={columns}
            rows={leads.data.items}
            rowKey={(lead) => lead.id}
            sort={list.sort}
            onSort={(sort) => {
              list.update({ sort })
            }}
            empty={
              <ListEmptyState
                filtered={list.filtered}
                onClear={list.clear}
                create={
                  can('records.create') ? { to: '/leads/new', label: t('list.new') } : undefined
                }
              />
            }
          />
          <Pagination
            page={list.page}
            pageSize={PAGE_SIZE}
            total={leads.data.total}
            onPageChange={(page) => {
              list.update({ page: String(page) })
            }}
          />
        </>
      ) : leads.isPending ? (
        <Loading variant="table" />
      ) : null}
    </section>
  )
}

export function LeadNewPage() {
  const notify = useNotify()
  const { t } = useTranslation('leads')
  const crumbs = useSectionCrumbs()
  const [params] = useSearchParams()
  const organizationId = params.get('organization_id')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const organization = useQuery({
    queryKey: ['organizations', organizationId],
    queryFn: () =>
      call(
        api.GET('/api/v1/organizations/{org_id}', {
          params: { path: { org_id: organizationId ?? '' } },
        }),
      ),
    enabled: organizationId !== null,
  })
  const create = useMutation({
    mutationFn: (values: LeadValues) =>
      call(api.POST('/api/v1/leads', { body: leadPayload(values) })),
    onSuccess: async (lead) => {
      await queryClient.invalidateQueries({ queryKey: ['leads'] })
      await queryClient.invalidateQueries({ queryKey: ['organizations'] })
      notify.success(t('toasts.created'))
      await navigate(`/leads/${lead.id}`)
    },
  })
  if (organizationId && organization.isPending) return <Loading variant="form" />
  const preset = organization.data
    ? { id: organization.data.id, name: organization.data.name }
    : null
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader title={t('createTitle')} breadcrumbs={[crumbs.leads]} />
      <Card>
        <CardContent>
          <LeadForm
            defaultValues={leadDefaults(undefined, preset)}
            submitLabel={t('create')}
            pending={create.isPending}
            onSubmit={(values) => create.mutateAsync(values)}
          />
        </CardContent>
      </Card>
    </section>
  )
}

export function LeadEditPage() {
  const notify = useNotify()
  const { leadId = '' } = useParams()
  const { t } = useTranslation('leads')
  const crumbs = useSectionCrumbs()
  const { t: tc } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const path = { params: { path: { lead_id: leadId } } }
  const lead = useQuery({
    queryKey: ['leads', leadId],
    queryFn: () => call(api.GET('/api/v1/leads/{lead_id}', path)),
  })
  const save = useMutation({
    mutationFn: (values: LeadValues) =>
      call(
        api.PATCH('/api/v1/leads/{lead_id}', {
          ...path,
          body: { ...leadPayload(values), version: lead.data?.version ?? 0 },
        }),
      ),
    onSuccess: async (updated) => {
      queryClient.setQueryData(['leads', leadId], updated)
      await queryClient.invalidateQueries({ queryKey: ['organizations'] })
      notify.success(t('toasts.saved'))
      await navigate(`/leads/${leadId}`)
    },
  })
  if (lead.isError)
    return (
      <ErrorState
        error={lead.error}
        onRetry={() => {
          void lead.refetch()
        }}
      />
    )
  if (!lead.data) return <Loading variant="form" />
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader
        title={t('editTitle')}
        breadcrumbs={[crumbs.leads, { label: lead.data.title, to: `/leads/${leadId}` }]}
      />
      <Card>
        <CardContent>
          <LeadForm
            key={lead.data.version}
            defaultValues={leadDefaults(lead.data)}
            submitLabel={tc('actions.save')}
            pending={save.isPending}
            onSubmit={(values) => save.mutateAsync(values)}
          />
        </CardContent>
      </Card>
    </section>
  )
}
