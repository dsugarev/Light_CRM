import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

/** A full-page message with a way home; UX-04 adds a retry and the request ID for support. */
export function ErrorMessage({
  message,
  requestId,
  onRetry,
}: {
  message: string
  requestId?: string | null | undefined
  onRetry?: (() => void) | undefined
}) {
  const { t } = useTranslation()
  return (
    <section
      role="alert"
      className="mx-auto mt-16 flex max-w-md flex-col items-center gap-4 text-center"
    >
      <p>{message}</p>
      {requestId ? (
        <p className="text-xs text-muted-foreground">
          {t('states.requestId')} <span className="font-mono select-all">{requestId}</span>
        </p>
      ) : null}
      <div className="flex flex-wrap items-center justify-center gap-4">
        {onRetry ? (
          <Button type="button" variant="outline" size="sm" onClick={onRetry}>
            {t('states.retry')}
          </Button>
        ) : null}
        <Link className="text-primary underline underline-offset-4" to="/">
          {t('errors.backHome')}
        </Link>
      </div>
    </section>
  )
}
