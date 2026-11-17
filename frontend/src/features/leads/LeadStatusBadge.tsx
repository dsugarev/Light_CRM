import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'

import type { Lead } from './leadValues'

const VARIANT = {
  new: 'secondary',
  contacted: 'secondary',
  qualified: 'default',
  converted: 'outline',
  disqualified: 'destructive',
} as const

export function LeadStatusBadge({ status }: { status: Lead['status'] }) {
  const { t } = useTranslation('leads')
  return <Badge variant={VARIANT[status]}>{t(`status.${status}`)}</Badge>
}
