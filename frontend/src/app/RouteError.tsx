import { useTranslation } from 'react-i18next'
import { isRouteErrorResponse, useRouteError } from 'react-router'

import { ApiError } from '@/api/client'
import { reloadPage } from '@/lib/reload'

import { ErrorMessage } from './ErrorMessage'
import { NotFoundPage } from './NotFoundPage'

// Error boundary for every route: shows a translated message, never error details;
// UX-04: a retry (reloads the page) and the request ID when the API gave one.
export function RouteError() {
  const { t } = useTranslation()
  const error = useRouteError()
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFoundPage />

  return (
    <ErrorMessage
      message={t('errors.unexpected')}
      requestId={error instanceof ApiError ? error.requestId : null}
      onRetry={reloadPage}
    />
  )
}
