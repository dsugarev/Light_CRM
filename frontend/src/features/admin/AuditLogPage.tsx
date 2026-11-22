import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import { api, call, type Schemas } from '@/api/client'
import { DataTable, type Column } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { Button, buttonVariants } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Sheet } from '@/components/ui/sheet'
import { DISPLAY_TIME_ZONE, formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'
import { ExportMenu } from '@/features/reports/ExportMenu'

import { AuditEntryDetails } from './AuditEntryDetails'
import { AUDIT_ENTITY_TYPES, useAuditLabels } from './auditLabels'

type Entry = Schemas['AuditEntrySummary']
const PAGE_SIZE = 50
const FILTERS = ['actor_id', 'action', 'entity_type', 'from', 'to'] as const
type Filter = (typeof FILTERS)[number]
type Values = Record<Filter, string>
const DAY = 86_400_000

/** Sofia-local date (YYYY-MM-DD) to the UTC instant at its start or end. */
function sofiaDayBoundary(date: string, end: boolean): string {
  const local = new Date(`${date}T${end ? '23:59:59' : '00:00:00'}Z`)
  const offset =
    new Date(local.toLocaleString('en-US', { timeZone: DISPLAY_TIME_ZONE })).getTime() -
    new Date(local.toLocaleString('en-US', { timeZone: 'UTC' })).getTime()
  return new Date(local.getTime() - offset).toISOString()
}

/** The Sofia calendar day `daysAgo` days before now, as YYYY-MM-DD. */
function sofiaDay(now: number, daysAgo: number): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: DISPLAY_TIME_ZONE }).format(
    new Date(now - daysAgo * DAY),
  )
}

/** UX-10 presets: today, the last 7 and the last 30 days, both ends included. */
const PRESETS = { today: 0, last7: 6, last30: 29 } as const

function presetRange(daysBack: number): { from: string; to: string } {
  const now = Date.now()
  return { from: sofiaDay(now, daysBack), to: sofiaDay(now, 0) }
}

/**
 * FR-ADM-03, UX-10: browse and filter by user, record type, action and date (with presets
 * for today, 7 and 30 days); an entry opens in a drawer with before and after side by side.
 * Filters and the open entry live in the URL. Read-only.
 */
export function AuditLogPage() {
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const labels = useAuditLabels()
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)
  const value = (name: Filter) => params.get(name) ?? ''
  const [draft, setDraft] = useState<Values>({
    actor_id: value('actor_id'),
    action: value('action'),
    entity_type: value('entity_type'),
    from: value('from'),
    to: value('to'),
  })
  const entityId = params.get('entity_id')
  const openId = params.get('entry')

  const filterQuery = {
    ...(value('action') ? { action: [value('action')] } : {}),
    ...(value('entity_type') ? { entity_type: value('entity_type') } : {}),
    ...(value('from') ? { occurred_at_from: sofiaDayBoundary(value('from'), false) } : {}),
    ...(value('to') ? { occurred_at_to: sofiaDayBoundary(value('to'), true) } : {}),
    ...(value('actor_id') ? { actor_id: value('actor_id') } : {}),
    ...(entityId ? { entity_id: entityId } : {}),
  }
  const listKey = new URLSearchParams(params)
  listKey.delete('entry')
  const entries = useQuery({
    queryKey: ['audit-log', listKey.toString()],
    // Keep showing the current rows while the next page or filter loads.
    placeholderData: keepPreviousData,
    queryFn: () =>
      call(
        api.GET('/api/v1/audit-log', {
          params: { query: { page, page_size: PAGE_SIZE, ...filterQuery } },
        }),
      ),
  })
  const users = useQuery({
    queryKey: ['users', 'audit-filter'],
    queryFn: () => call(api.GET('/api/v1/users', { params: { query: { page_size: 100 } } })),
    staleTime: 300_000,
  })
  const entry = useQuery({
    queryKey: ['audit-log', 'entry', openId],
    enabled: openId !== null,
    queryFn: () =>
      call(
        api.GET('/api/v1/audit-log/{entry_id}', {
          params: { path: { entry_id: openId ?? '' } },
        }),
      ),
  })

  const apply = (values: Values) => {
    const next = new URLSearchParams()
    for (const name of FILTERS) if (values[name].trim()) next.set(name, values[name].trim())
    if (entityId) next.set('entity_id', entityId)
    setParams(next, { replace: true })
  }
  const preset = (daysBack: number) => {
    const values = { ...draft, ...presetRange(daysBack) }
    setDraft(values)
    apply(values)
  }
  const withEntry = (id: string | null) => {
    const next = new URLSearchParams(params)
    if (id) next.set('entry', id)
    else next.delete('entry')
    return `?${next.toString()}`
  }

  const columns: Column<Entry>[] = [
    {
      key: 'time',
      header: t('audit.columns.time'),
      cell: (row) => {
        const time = formatDateTime(row.occurred_at, locale)
        return (
          <Link
            to={withEntry(row.id)}
            aria-label={t('audit.open', { time })}
            className="hover:underline"
          >
            {time}
          </Link>
        )
      },
    },
    {
      key: 'actor',
      header: t('audit.columns.actor'),
      className: 'whitespace-normal [overflow-wrap:anywhere]',
      cell: (row) => labels.actor(row.actor),
    },
    {
      key: 'action',
      header: t('audit.columns.action'),
      className: 'whitespace-normal [overflow-wrap:anywhere]',
      cell: (row) => labels.action(row.action),
    },
    {
      key: 'entity',
      header: t('audit.columns.entity'),
      className: 'whitespace-normal [overflow-wrap:anywhere]',
      cell: (row) => (
        <>
          {labels.entityType(row.entity_type)}
          {row.entity_id ? (
            <span className="ml-1 font-mono text-xs text-muted-foreground">
              {row.entity_id.slice(0, 8)}
            </span>
          ) : null}
        </>
      ),
    },
    {
      key: 'ip',
      header: t('audit.columns.ip'),
      className: 'hidden lg:table-cell',
      cell: (row) => row.ip ?? '',
    },
  ]

  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader
        title={t('audit.title')}
        actions={<ExportMenu path="/api/v1/audit-log/export" query={filterQuery} />}
      />
      <form
        className="mb-2 grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_auto_auto]"
        onSubmit={(event) => {
          event.preventDefault()
          apply(draft)
        }}
      >
        <FormField label={t('audit.user')}>
          {(control) => (
            <NativeSelect
              {...control}
              value={draft.actor_id}
              onChange={(e) => {
                setDraft({ ...draft, actor_id: e.target.value })
              }}
            >
              <option value="">{t('audit.allUsers')}</option>
              {(users.data?.items ?? []).map((user) => (
                <option key={user.id} value={user.id}>
                  {user.full_name}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <FormField label={t('audit.entityType')}>
          {(control) => (
            <NativeSelect
              {...control}
              value={draft.entity_type}
              onChange={(e) => {
                setDraft({ ...draft, entity_type: e.target.value })
              }}
            >
              <option value="">{t('audit.allTypes')}</option>
              {AUDIT_ENTITY_TYPES.map((type) => (
                <option key={type} value={type}>
                  {labels.entityType(type)}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <FormField label={t('audit.action')}>
          {(control) => (
            <Input
              {...control}
              placeholder={t('audit.actionHint')}
              value={draft.action}
              onChange={(e) => {
                setDraft({ ...draft, action: e.target.value })
              }}
            />
          )}
        </FormField>
        <FormField label={t('audit.from')}>
          {(control) => (
            <Input
              {...control}
              type="date"
              value={draft.from}
              onChange={(e) => {
                setDraft({ ...draft, from: e.target.value })
              }}
            />
          )}
        </FormField>
        <FormField label={t('audit.to')}>
          {(control) => (
            <Input
              {...control}
              type="date"
              value={draft.to}
              onChange={(e) => {
                setDraft({ ...draft, to: e.target.value })
              }}
            />
          )}
        </FormField>
        <div className="flex flex-wrap items-center gap-2 sm:col-span-2 lg:col-span-5">
          <Button type="submit">{t('audit.filter')}</Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              const empty = { actor_id: '', action: '', entity_type: '', from: '', to: '' }
              setDraft(empty)
              setParams(new URLSearchParams(), { replace: true })
            }}
          >
            {t('audit.reset')}
          </Button>
          <div role="group" aria-label={t('audit.presets')} className="flex flex-wrap gap-1">
            {(Object.entries(PRESETS) as [keyof typeof PRESETS, number][]).map(([name, days]) => (
              <Button
                key={name}
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  preset(days)
                }}
              >
                {t(`audit.${name}`)}
              </Button>
            ))}
          </div>
        </div>
      </form>
      {entries.isError ? (
        <ErrorState
          error={entries.error}
          onRetry={() => {
            void entries.refetch()
          }}
        />
      ) : entries.data ? (
        <>
          <DataTable
            busy={entries.isPlaceholderData}
            caption={t('audit.title')}
            columns={columns}
            rows={entries.data.items}
            rowKey={(row) => row.id}
            sort="-occurred_at"
            onSort={() => undefined}
          />
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={entries.data.total}
            onPageChange={(p) => {
              const next = new URLSearchParams(params)
              next.set('page', String(p))
              setParams(next, { replace: true })
            }}
          />
        </>
      ) : (
        <Loading variant="table" />
      )}
      <Sheet
        open={openId !== null}
        onOpenChange={(open) => {
          if (!open) setParams(new URLSearchParams(withEntry(null)), { replace: true })
        }}
        title={entry.data ? labels.action(entry.data.action) : t('audit.detail.title')}
        closeLabel={tc('actions.close')}
        className="sm:w-[44rem]"
      >
        {entry.isError ? (
          <ErrorState error={entry.error} />
        ) : entry.data ? (
          <>
            <AuditEntryDetails entry={entry.data} />
            <Link
              to={`/admin/audit-log/${entry.data.id}`}
              className={buttonVariants({ variant: 'outline', className: 'self-start' })}
            >
              {t('audit.detail.openPage')}
            </Link>
          </>
        ) : (
          <Loading />
        )}
      </Sheet>
    </section>
  )
}
