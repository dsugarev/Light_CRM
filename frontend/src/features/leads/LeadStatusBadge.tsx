import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'

import type { Lead } from './leadValues'

// Loop 2: new is blue (needs attention), in progress neutral, qualified green, closed
// outcomes outlined (converted) or red (disqualified). The label always shows.
const VARIANT = {
  new: 'info',
  contacted: 'secondary',
  qualified: 'success',
  converted: 'outline',
  disqualified: 'destructive',
} as const

export function LeadStatusBadge({ status }: { status: Lead['status'] }) {
  const { t } = useTranslation('leads')
  return <Badge variant={VARIANT[status]}>{t(`status.${status}`)}</Badge>
}
