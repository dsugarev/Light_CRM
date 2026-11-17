import { useTranslation } from 'react-i18next'

import { useApiHealth } from './useApiHealth'

export function ApiStatus() {
  const { t } = useTranslation()
  const { data, isPending } = useApiHealth()
  const label = isPending ? t('apiStatus.checking') : t(`apiStatus.${data ?? 'unavailable'}`)
  const dot = data === 'ok' ? 'bg-emerald-500' : isPending ? 'bg-muted-foreground' : 'bg-red-500'

  return (
    <p className="flex items-center gap-2 text-xs text-muted-foreground" data-testid="api-status">
      <span aria-hidden="true" className={`size-2 rounded-full ${dot}`} />
      <span>
        {t('apiStatus.label')}: {label}
      </span>
    </p>
  )
}
