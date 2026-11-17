import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { Loading } from '@/components/Loading'
import { Pagination } from '@/components/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { referenceName } from '@/features/reference/useReferenceList'
import { formatDateTime } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useLocale } from '@/lib/useLocale'

import { ActivityForm } from './ActivityForm'
import type { Activity, RecordRef, TimelineItem } from './activityValues'
import { TaskCheckbox } from './TaskCheckbox'
import { useTimeline } from './useTimeline'

const PAGE_SIZE = 20
const RECORD_PATHS = {
  lead: '/leads',
  opportunity: '/opportunities',
  organization: '/organizations',
  contact: '/contacts',
} as const

/** FR-ACT-03: the record's activities and system events, newest first, with "Log activity". */
export function RecordTimeline({ record, canLog }: { record: RecordRef; canLog: boolean }) {
  const { t } = useTranslation('activities')
  const can = useCan()
  const [page, setPage] = useState(1)
  const [logging, setLogging] = useState(false)
  const timeline = useTimeline(record, page, PAGE_SIZE)
  const mayLog = canLog && can('records.create')
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t('timeline.title')}</CardTitle>
        {mayLog && !logging ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              setLogging(true)
            }}
          >
            {t('timeline.log')}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {logging ? (
          <ActivityForm
            record={record}
            onDone={() => {
              setLogging(false)
              setPage(1)
            }}
          />
        ) : null}
        {timeline.data ? (
          timeline.data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('timeline.empty')}</p>
          ) : (
            <>
              <ol className="flex flex-col gap-3" aria-label={t('timeline.title')}>
                {timeline.data.items.map((item) => (
                  <li key={item.id} className="border-l-2 pl-3">
                    {item.activity ? (
                      <ActivityEntry activity={item.activity} record={record} />
                    ) : (
                      <EventEntry item={item} record={record} />
                    )}
                  </li>
                ))}
              </ol>
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={timeline.data.total}
                onPageChange={setPage}
              />
            </>
          )
        ) : (
          <Loading />
        )}
      </CardContent>
    </Card>
  )
}

function ActivityEntry({ activity: a, record }: { activity: Activity; record: RecordRef }) {
  const { t } = useTranslation('activities')
  const locale = useLocale()
  const other = (['lead', 'opportunity', 'organization', 'contact'] as const)
    .map((kind) => ({ kind, link: a.links[kind] }))
    .filter(({ kind, link }) => link && !(kind === record.kind && link.id === record.id))
  return (
    <div className="flex flex-col gap-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{t(`type.${a.type}`)}</Badge>
        {a.type === 'task' ? <TaskCheckbox task={a} /> : null}
        <span className={a.is_done ? 'font-medium line-through' : 'font-medium'}>{a.subject}</span>
        {a.is_overdue ? <Badge variant="destructive">{t('task.overdue')}</Badge> : null}
      </div>
      {a.body ? <p className="whitespace-pre-wrap">{a.body}</p> : null}
      <p className="text-xs text-muted-foreground">
        {a.type === 'task'
          ? t('task.meta', {
              due: a.due_at ? formatDateTime(a.due_at, locale) : '',
              assignee: a.assignee?.full_name ?? '',
            })
          : t('timeline.meta', {
              when: formatDateTime(a.occurred_at, locale),
              who: a.owner.full_name,
            })}
        {other.map(({ kind, link }) =>
          link ? (
            <span key={kind}>
              {' · '}
              <Link className="hover:underline" to={`${RECORD_PATHS[kind]}/${link.id}`}>
                {`${t(`entity.${kind}`)}: ${link.name}`}
              </Link>
            </span>
          ) : null,
        )}
      </p>
    </div>
  )
}

interface Named {
  name_en: string
  name_bg: string
}

function named(value: unknown): Named | null {
  return value && typeof value === 'object' && 'name_en' in value ? (value as Named) : null
}

function person(value: unknown): string {
  return value && typeof value === 'object' && 'full_name' in value ? String(value.full_name) : ''
}

/** Text for one system event (API spec 11: created, stage_changed, converted, ...). */
function EventEntry({ item, record }: { item: TimelineItem; record: RecordRef }) {
  const { t } = useTranslation('activities')
  const { t: tl } = useTranslation('leads')
  const locale = useLocale()
  const event = item.event
  if (!event) return null
  const data = event.data
  const name = (value: unknown) => {
    const n = named(value)
    return n ? referenceName(n, locale) : ''
  }
  const status = (value: unknown) =>
    typeof value === 'string' ? tl(`status.${value}` as 'status.new') : ''
  const opportunity = data['opportunity'] as { id: string; name: string } | undefined
  let text: string
  switch (event.type) {
    case 'owner_changed':
      text = t('event.owner_changed', {
        from: person(data['from_owner']),
        to: person(data['to_owner']),
      })
      break
    case 'status_changed':
      text = t('event.status_changed', {
        from: status(data['from_status']),
        to: status(data['to_status']),
      })
      break
    case 'stage_changed':
      text = t('event.stage_changed', {
        from: name(data['from_stage']),
        to: name(data['to_stage']),
      })
      break
    case 'closed_lost':
      text = t('event.closed_lost', { reason: name(data['loss_reason']) })
      break
    case 'reopened':
      text = t('event.reopened', { to: name(data['to_stage']) })
      break
    case 'created':
    case 'updated':
    case 'converted':
    case 'closed_won':
    case 'archived':
    case 'restored':
      text = t(`event.${event.type}`)
      break
    default:
      text = event.type
  }
  const elsewhere = event.entity_type !== record.kind || event.entity_id !== record.id
  return (
    <div className="flex flex-col gap-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{t(`entity.${event.entity_type as RecordRef['kind']}`)}</Badge>
        <span>{text}</span>
        {opportunity ? (
          <Link className="hover:underline" to={`/opportunities/${opportunity.id}`}>
            {opportunity.name}
          </Link>
        ) : null}
        {elsewhere ? (
          <Link
            className="text-xs text-muted-foreground hover:underline"
            to={`${RECORD_PATHS[event.entity_type as RecordRef['kind']]}/${event.entity_id}`}
          >
            {t('timeline.open')}
          </Link>
        ) : null}
      </div>
      <p className="text-xs text-muted-foreground">
        {t('timeline.meta', {
          when: formatDateTime(item.occurred_at, locale),
          who: item.actor?.full_name ?? '',
        })}
      </p>
    </div>
  )
}
