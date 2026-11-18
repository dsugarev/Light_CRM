import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router'

import { api, call } from '@/api/client'
import { FormField } from '@/components/FormField'
import { EmptyState } from '@/components/EmptyState'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { DISPLAY_TIME_ZONE, formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'
import { ExportMenu } from '@/features/reports/ExportMenu'

import { useAuditLabels } from './auditLabels'

const PAGE_SIZE = 50
const FILTERS = ['action', 'entity_type', 'from', 'to'] as const
type Filter = (typeof FILTERS)[number]

/** Sofia-local date (YYYY-MM-DD) to the UTC instant at its start or end. */
function sofiaDayBoundary(date: string, end: boolean): string {
  const local = new Date(`${date}T${end ? '23:59:59' : '00:00:00'}Z`)
  const offset =
    new Date(local.toLocaleString('en-US', { timeZone: DISPLAY_TIME_ZONE })).getTime() -
    new Date(local.toLocaleString('en-US', { timeZone: 'UTC' })).getTime()
  return new Date(local.getTime() - offset).toISOString()
}

/** FR-ADM-03: browse and filter by user, record, action and date. Read-only. */
export function AuditLogPage() {
  const { t } = useTranslation('admin')
  const locale = useLocale()
  const labels = useAuditLabels()
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)
  const value = (name: Filter) => params.get(name) ?? ''
  const [draft, setDraft] = useState<Record<Filter, string>>({
    action: value('action'),
    entity_type: value('entity_type'),
    from: value('from'),
    to: value('to'),
  })
  const filterFields = [
    ['action', t('audit.action'), 'text'],
    ['entity_type', t('audit.entityType'), 'text'],
    ['from', t('audit.from'), 'date'],
    ['to', t('audit.to'), 'date'],
  ] as const
  const actorId = params.get('actor_id')
  const entityId = params.get('entity_id')

  const filterQuery = {
    ...(value('action') ? { action: [value('action')] } : {}),
    ...(value('entity_type') ? { entity_type: value('entity_type') } : {}),
    ...(value('from') ? { occurred_at_from: sofiaDayBoundary(value('from'), false) } : {}),
    ...(value('to') ? { occurred_at_to: sofiaDayBoundary(value('to'), true) } : {}),
    ...(actorId ? { actor_id: actorId } : {}),
    ...(entityId ? { entity_id: entityId } : {}),
  }
  const entries = useQuery({
    queryKey: ['audit-log', params.toString()],
    // Keep showing the current rows while the next page, sort or filter loads.
    placeholderData: keepPreviousData,
    queryFn: () =>
      call(
        api.GET('/api/v1/audit-log', {
          params: {
            query: { page, page_size: PAGE_SIZE, ...filterQuery },
          },
        }),
      ),
  })

  const apply = (values: Record<Filter, string>) => {
    const next = new URLSearchParams()
    for (const name of FILTERS) if (values[name].trim()) next.set(name, values[name].trim())
    if (actorId) next.set('actor_id', actorId)
    if (entityId) next.set('entity_id', entityId)
    setParams(next, { replace: true })
  }

  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader
        title={t('audit.title')}
        actions={<ExportMenu path="/api/v1/audit-log/export" query={filterQuery} />}
      />
      <form
        className="mb-4 grid items-end gap-3 sm:grid-cols-[1fr_1fr_1fr_1fr_auto_auto]"
        onSubmit={(event) => {
          event.preventDefault()
          apply(draft)
        }}
      >
        {filterFields.map(([name, label, type]) => (
          <FormField key={name} label={label}>
            {(control) => (
              <Input
                {...control}
                type={type}
                value={draft[name]}
                onChange={(e) => {
                  setDraft({ ...draft, [name]: e.target.value })
                }}
              />
            )}
          </FormField>
        ))}
        <Button type="submit">{t('audit.filter')}</Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            const empty = { action: '', entity_type: '', from: '', to: '' }
            setDraft(empty)
            setParams(new URLSearchParams(), { replace: true })
          }}
        >
          {t('audit.reset')}
        </Button>
      </form>
      {entries.data ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('audit.columns.time')}</TableHead>
                <TableHead>{t('audit.columns.actor')}</TableHead>
                <TableHead>{t('audit.columns.action')}</TableHead>
                <TableHead>{t('audit.columns.entity')}</TableHead>
                <TableHead>{t('audit.columns.ip')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.data.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5}>
                    <EmptyState />
                  </TableCell>
                </TableRow>
              ) : (
                entries.data.items.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>
                      <Link to={`/admin/audit-log/${entry.id}`} className="hover:underline">
                        {formatDateTime(entry.occurred_at, locale)}
                      </Link>
                    </TableCell>
                    <TableCell>{labels.actor(entry.actor)}</TableCell>
                    <TableCell>{labels.action(entry.action)}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {entry.entity_type}
                      {entry.entity_id ? ` ${entry.entity_id.slice(0, 8)}` : ''}
                    </TableCell>
                    <TableCell>{entry.ip ?? ''}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
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
    </section>
  )
}
