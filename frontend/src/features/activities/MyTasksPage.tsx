import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { api, call } from '@/api/client'
import { DataTable, type Column } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { Badge } from '@/components/ui/badge'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import type { Activity } from './activityValues'
import { TaskCheckbox } from './TaskCheckbox'

const PAGE_SIZE = 25
const RECORD_PATHS = {
  lead: '/leads',
  opportunity: '/opportunities',
  organization: '/organizations',
  contact: '/contacts',
} as const

/** FR-ACT-02: "My tasks", open ones first, overdue at the top. */
export function MyTasksPage() {
  const { t } = useTranslation('activities')
  const locale = useLocale()
  const [page, setPage] = useState(1)
  const [includeDone, setIncludeDone] = useState(false)
  const tasks = useQuery({
    queryKey: ['tasks', page, includeDone],
    placeholderData: keepPreviousData,
    queryFn: () =>
      call(
        api.GET('/api/v1/me/tasks', {
          params: { query: { page, page_size: PAGE_SIZE, include_done: includeDone } },
        }),
      ),
  })
  const columns: Column<Activity>[] = [
    { key: 'done', header: t('tasks.columns.done'), cell: (task) => <TaskCheckbox task={task} /> },
    {
      key: 'subject',
      header: t('tasks.columns.subject'),
      cell: (task) => (
        <span className={task.is_done ? 'line-through' : 'font-medium'}>{task.subject}</span>
      ),
    },
    {
      key: 'due',
      header: t('tasks.columns.due'),
      cell: (task) => (
        <span className="flex items-center gap-2">
          {task.due_at ? formatDateTime(task.due_at, locale) : ''}
          {task.is_overdue ? <Badge variant="destructive">{t('task.overdue')}</Badge> : null}
        </span>
      ),
    },
    {
      key: 'record',
      header: t('tasks.columns.record'),
      cell: (task) => {
        const found = (['opportunity', 'lead', 'organization', 'contact'] as const)
          .map((kind) => ({ kind, link: task.links[kind] }))
          .find(({ link }) => link)
        return found?.link ? (
          <Link
            className="hover:underline"
            to={`${RECORD_PATHS[found.kind]}/${found.link.id}`}
          >{`${t(`entity.${found.kind}`)}: ${found.link.name}`}</Link>
        ) : null
      },
    },
    { key: 'owner', header: t('tasks.columns.owner'), cell: (task) => task.owner.full_name },
  ]
  return (
    <section className="mx-auto max-w-5xl">
      <PageHeader title={t('tasks.title')} />
      <label className="mb-4 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={includeDone}
          onChange={(e) => {
            setIncludeDone(e.target.checked)
            setPage(1)
          }}
        />
        {t('tasks.includeDone')}
      </label>
      {tasks.isError ? (
        <ErrorState
          error={tasks.error}
          onRetry={() => {
            void tasks.refetch()
          }}
        />
      ) : null}
      {tasks.data ? (
        <>
          <DataTable
            busy={tasks.isPlaceholderData}
            caption={t('tasks.title')}
            columns={columns}
            rows={tasks.data.items}
            rowKey={(task) => task.id}
            sort="due_at"
            onSort={() => undefined}
            empty={t('tasks.none')}
          />
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={tasks.data.total}
            onPageChange={setPage}
          />
        </>
      ) : tasks.isPending ? (
        <Loading variant="table" />
      ) : null}
    </section>
  )
}
