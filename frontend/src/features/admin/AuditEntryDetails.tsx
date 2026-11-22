import { useTranslation } from 'react-i18next'

import type { Schemas } from '@/api/client'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'
import { detailListClass } from '@/components/detailList'

import { AuditDiff, AuditJson } from './AuditDiff'
import { useAuditLabels } from './auditLabels'

/** UX-10: one audit entry: who, when, which record, the changes and any details. */
export function AuditEntryDetails({ entry: e }: { entry: Schemas['AuditEntry'] }) {
  const { t } = useTranslation('admin')
  const locale = useLocale()
  const labels = useAuditLabels()
  const details = e.details as unknown
  return (
    <div className="flex flex-col gap-6">
      <dl className={detailListClass('compact')}>
        <dt className="text-muted-foreground">{t('audit.columns.time')}</dt>
        <dd>{formatDateTime(e.occurred_at, locale)}</dd>
        <dt className="text-muted-foreground">{t('audit.columns.actor')}</dt>
        <dd>{labels.actor(e.actor)}</dd>
        <dt className="text-muted-foreground">{t('audit.columns.entity')}</dt>
        <dd className="[overflow-wrap:anywhere]">
          {labels.entityType(e.entity_type)}{' '}
          <span className="font-mono text-xs">{e.entity_id ?? ''}</span>
        </dd>
        <dt className="text-muted-foreground">{t('audit.columns.ip')}</dt>
        <dd>{e.ip ?? t('audit.detail.none')}</dd>
        <dt className="text-muted-foreground">{t('audit.detail.requestId')}</dt>
        <dd className="font-mono text-xs">{e.request_id ?? t('audit.detail.none')}</dd>
      </dl>
      <section className="flex flex-col gap-2">
        <h2 className="text-base font-semibold">{t('audit.detail.changes')}</h2>
        <AuditDiff before={e.before} after={e.after} />
      </section>
      {details != null && !(typeof details === 'object' && Object.keys(details).length === 0) ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">{t('audit.detail.details')}</h2>
          <AuditJson value={details} />
        </section>
      ) : null}
    </div>
  )
}
