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
import { formatDay, formatMoney } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useListParams } from '@/lib/useListParams'
import { useLocale } from '@/lib/useLocale'
import { ExportMenu } from '@/features/reports/ExportMenu'
import { useNotify } from '@/lib/notify'

import { OpportunityForm } from './OpportunityForm'
import {
  opportunityDefaults,
  opportunityPayload,
  stageName,
  STAGE_TYPES,
  type Opportunity,
  type OpportunityValues,
} from './opportunityValues'
import { StageBadge, StaleBadge } from './StageBadge'
import { usePipeline } from './usePipeline'

const PAGE_SIZE = 25

/** FR-OPP-04: sortable, filterable list; filters in the URL. */
export function OpportunitiesPage() {
  const { t } = useTranslation('opportunities')
  const locale = useLocale()
  const can = useCan()
  const pipeline = usePipeline()
  const list = useListParams({
    sort: '-updated_at',
    filters: ['stage_id', 'stage_type', 'owner_id', 'is_stale'] as const,
  })
  const opportunities = useQuery({
    queryKey: ['opportunities', 'list', list.key],
    placeholderData: keepPreviousData,
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/opportunities', {
            params: { query: { ...list.apiQuery, page_size: PAGE_SIZE } },
          }),
        ),
      ),
  })
  const columns: Column<Opportunity>[] = [
    {
      key: 'name',
      className: 'whitespace-normal',
      header: t('list.columns.name'),
      sortKey: 'name',
      cell: (o) => (
        <span className="flex items-center gap-2">
          <Link to={`/opportunities/${o.id}`} className="font-medium hover:underline">
            {o.name}
          </Link>
          {o.is_stale ? <StaleBadge /> : null}
          {o.archived_at ? <Badge variant="outline">{t('list.archived')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'organization',
      className: 'whitespace-normal',
      header: t('list.columns.organization'),
      cell: (o) => (
        <Link to={`/organizations/${o.organization.id}`} className="hover:underline">
          {o.organization.name}
        </Link>
      ),
    },
    { key: 'stage', header: t('list.columns.stage'), cell: (o) => <StageBadge stage={o.stage} /> },
    {
      key: 'amount',
      header: t('list.columns.amount'),
      sortKey: 'amount',
      cell: (o) => (o.amount ? formatMoney(o.amount, locale) : ''),
      className: 'text-right',
    },
    {
      key: 'probability',
      header: t('list.columns.probability'),
      cell: (o) => `${String(o.probability)}%`,
      className: 'text-right hidden lg:table-cell',
    },
    {
      key: 'weighted',
      header: t('list.columns.weighted'),
      cell: (o) => (o.weighted_amount ? formatMoney(o.weighted_amount, locale) : ''),
      className: 'text-right hidden lg:table-cell',
    },
    {
      key: 'close',
      header: t('list.columns.expectedClose'),
      sortKey: 'expected_close_date',
      cell: (o) => (o.expected_close_date ? formatDay(o.expected_close_date, locale) : ''),
    },
    {
      key: 'owner',
      className: 'hidden lg:table-cell',
      header: t('list.columns.owner'),
      cell: (o) => o.owner.full_name,
    },
  ]
  return (
    <section className="mx-auto max-w-7xl">
      <PageHeader
        title={t('list.title')}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ExportMenu path="/api/v1/opportunities/export" query={list.apiQuery} />
            <Link to="/opportunities/board" className={buttonVariants({ variant: 'outline' })}>
              {t('board.title')}
            </Link>
            {can('records.create') ? (
              <Link to="/opportunities/new" className={buttonVariants()}>
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
          aria-label={t('list.stage')}
          value={list.filters.stage_id[0] ?? ''}
          onChange={(e) => {
            list.update({ stage_id: e.target.value || null })
          }}
        >
          <option value="">{t('list.allStages')}</option>
          {(pipeline.data?.stages ?? []).map((stage) => (
            <option key={stage.id} value={stage.id}>
              {stageName(stage, locale)}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label={t('list.stageType')}
          value={list.filters.stage_type[0] ?? ''}
          onChange={(e) => {
            list.update({ stage_type: e.target.value || null })
          }}
        >
          <option value="">{t('list.allTypes')}</option>
          {STAGE_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(`stageType.${type}`)}
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
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={list.filters.is_stale[0] === 'true'}
            onChange={(e) => {
              list.update({ is_stale: e.target.checked ? 'true' : null })
            }}
          />
          {t('list.staleOnly')}
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
      {opportunities.isError ? (
        <ErrorState
          error={opportunities.error}
          onRetry={() => {
            void opportunities.refetch()
          }}
        />
      ) : null}
      {opportunities.data ? (
        <>
          <DataTable
            caption={t('list.title')}
            columns={columns}
            rows={opportunities.data.items}
            rowKey={(o) => o.id}
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
                    ? { to: '/opportunities/new', label: t('list.new') }
                    : undefined
                }
              />
            }
          />
          <Pagination
            page={list.page}
            pageSize={PAGE_SIZE}
            total={opportunities.data.total}
            onPageChange={(page) => {
              list.update({ page: String(page) })
            }}
          />
        </>
      ) : opportunities.isPending ? (
        <Loading variant="table" />
      ) : null}
    </section>
  )
}

export function OpportunityNewPage() {
  const notify = useNotify()
  const { t } = useTranslation('opportunities')
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
    mutationFn: (values: OpportunityValues) =>
      call(
        api.POST('/api/v1/opportunities', {
          body: { ...opportunityPayload(values), organization_id: values.organization?.id ?? '' },
        }),
      ),
    onSuccess: async (opportunity) => {
      await queryClient.invalidateQueries({ queryKey: ['opportunities'] })
      await queryClient.invalidateQueries({ queryKey: ['organizations'] })
      notify.success(t('toasts.created'))
      await navigate(`/opportunities/${opportunity.id}`)
    },
  })
  if (organizationId && organization.isPending) return <Loading variant="form" />
  const preset = organization.data
    ? { id: organization.data.id, name: organization.data.name }
    : null
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader title={t('createTitle')} breadcrumbs={[crumbs.opportunities]} />
      <Card>
        <CardContent>
          <OpportunityForm
            defaultValues={opportunityDefaults(undefined, preset)}
            organizationFixed={false}
            submitLabel={t('create')}
            pending={create.isPending}
            onSubmit={(values) => create.mutateAsync(values)}
          />
        </CardContent>
      </Card>
    </section>
  )
}

export function OpportunityEditPage() {
  const notify = useNotify()
  const { opportunityId = '' } = useParams()
  const { t } = useTranslation('opportunities')
  const crumbs = useSectionCrumbs()
  const { t: tc } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const path = { params: { path: { opp_id: opportunityId } } }
  const opportunity = useQuery({
    queryKey: ['opportunities', opportunityId],
    queryFn: () => call(api.GET('/api/v1/opportunities/{opp_id}', path)),
  })
  const save = useMutation({
    mutationFn: (values: OpportunityValues) =>
      call(
        api.PATCH('/api/v1/opportunities/{opp_id}', {
          ...path,
          body: { ...opportunityPayload(values), version: opportunity.data?.version ?? 0 },
        }),
      ),
    onSuccess: async (updated) => {
      queryClient.setQueryData(['opportunities', opportunityId], updated)
      await queryClient.invalidateQueries({ queryKey: ['organizations'] })
      notify.success(t('toasts.saved'))
      await navigate(`/opportunities/${opportunityId}`)
    },
  })
  if (opportunity.isError)
    return (
      <ErrorState
        error={opportunity.error}
        onRetry={() => {
          void opportunity.refetch()
        }}
      />
    )
  if (!opportunity.data) return <Loading variant="form" />
  return (
    <section className="mx-auto max-w-3xl">
      <PageHeader
        title={t('editTitle')}
        breadcrumbs={[
          crumbs.opportunities,
          { label: opportunity.data.name, to: `/opportunities/${opportunityId}` },
        ]}
      />
      <Card>
        <CardContent>
          <OpportunityForm
            key={opportunity.data.version}
            defaultValues={opportunityDefaults(opportunity.data)}
            organizationFixed
            submitLabel={tc('actions.save')}
            pending={save.isPending}
            onSubmit={(values) => save.mutateAsync(values)}
          />
        </CardContent>
      </Card>
    </section>
  )
}
