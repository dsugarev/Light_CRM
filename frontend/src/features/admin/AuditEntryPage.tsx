import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'

import { api, call } from '@/api/client'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { useSectionCrumbs } from '@/components/useSectionCrumbs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { useAuditLabels } from './auditLabels'

function Json({ value }: { value: unknown }) {
  const { t } = useTranslation('admin')
  if (value === null || value === undefined)
    return <p className="text-muted-foreground">{t('audit.detail.none')}</p>
  // Rendered as text: React escapes it; never interpreted as HTML.
  return (
    <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function AuditEntryPage() {
  const { entryId = '' } = useParams()
  const { t } = useTranslation('admin')
  const crumbs = useSectionCrumbs()
  const locale = useLocale()
  const labels = useAuditLabels()
  const entry = useQuery({
    queryKey: ['audit-log', 'entry', entryId],
    queryFn: () =>
      call(api.GET('/api/v1/audit-log/{entry_id}', { params: { path: { entry_id: entryId } } })),
  })
  if (!entry.data) return entry.isError ? <FormMessage error="resource.not_found" /> : <Loading />
  const e = entry.data
  const sections = [
    ['before', e.before],
    ['after', e.after],
    ['details', e.details],
  ] as const
  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader title={labels.action(e.action)} breadcrumbs={[crumbs.auditLog]} />
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">{t('audit.columns.time')}</dt>
        <dd>{formatDateTime(e.occurred_at, locale)}</dd>
        <dt className="text-muted-foreground">{t('audit.columns.actor')}</dt>
        <dd>{labels.actor(e.actor)}</dd>
        <dt className="text-muted-foreground">{t('audit.columns.entity')}</dt>
        <dd className="font-mono text-xs">
          {e.entity_type} {e.entity_id ?? ''}
        </dd>
        <dt className="text-muted-foreground">{t('audit.columns.ip')}</dt>
        <dd>{e.ip ?? t('audit.detail.none')}</dd>
        <dt className="text-muted-foreground">{t('audit.detail.requestId')}</dt>
        <dd className="font-mono text-xs">{e.request_id ?? t('audit.detail.none')}</dd>
      </dl>
      {sections.map(([name, value]) => (
        <Card key={name}>
          <CardHeader>
            <CardTitle>{t(`audit.detail.${name}`)}</CardTitle>
          </CardHeader>
          <CardContent>
            <Json value={value} />
          </CardContent>
        </Card>
      ))}
    </section>
  )
}
