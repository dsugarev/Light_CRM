import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { useLocale } from '@/lib/useLocale'

import { stageName, type StageSummary } from './opportunityValues'

// Loop 2: open stages blue, won green, lost red.
const VARIANT = { open: 'info', won: 'success', lost: 'destructive' } as const

export function StageBadge({ stage }: { stage: StageSummary }) {
  const locale = useLocale()
  return <Badge variant={VARIANT[stage.stage_type]}>{stageName(stage, locale)}</Badge>
}

/** FR-OPP-06: marks an opportunity with no recent activity or a passed close date. */
export function StaleBadge() {
  const { t } = useTranslation('opportunities')
  return (
    <Badge variant="warning" title={t('stale.hint')}>
      {t('stale.label')}
    </Badge>
  )
}
