import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'
import { FormMessage } from '@/components/FormMessage'
import { Button } from '@/components/ui/button'

/**
 * UX-04: translated message for a failed query (never raw error details), the request
 * ID to quote to support, and a retry button when the caller can refetch.
 */
export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation()
  const requestId = error instanceof ApiError ? error.requestId : null
  return (
    <div className="flex flex-col items-start gap-3">
      <FormMessage error={error instanceof ApiError ? error.code : 'unknown'} />
      {requestId ? (
        <p className="text-xs text-muted-foreground">
          {t('states.requestId')} <span className="font-mono select-all">{requestId}</span>
        </p>
      ) : null}
      {onRetry ? (
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          {t('states.retry')}
        </Button>
      ) : null}
    </div>
  )
}
