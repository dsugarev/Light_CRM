import { useTranslation } from 'react-i18next'

import type { Schemas } from '@/api/client'
import { Badge } from '@/components/ui/badge'

type ImportStatus = Schemas['ImportBatchOut']['status']

// Loop 2: steps still to finish are blue, imported is green, rolled back is outlined.
const VARIANT = {
  uploaded: 'info',
  mapped: 'info',
  validated: 'info',
  committed: 'success',
  rolled_back: 'outline',
} as const satisfies Record<ImportStatus, string>

export function ImportStatusBadge({ status }: { status: ImportStatus }) {
  const { t } = useTranslation('imports')
  return <Badge variant={VARIANT[status]}>{t(`status.${status}`)}</Badge>
}
