import { useTranslation } from 'react-i18next'
import { isRouteErrorResponse, useRouteError } from 'react-router'

import { ErrorMessage } from './ErrorMessage'
import { NotFoundPage } from './NotFoundPage'

// Error boundary for every route: shows a translated message, never error details.
export function RouteError() {
  const { t } = useTranslation()
  const error = useRouteError()
  if (isRouteErrorResponse(error) && error.status === 404) return <NotFoundPage />

  return <ErrorMessage message={t('errors.unexpected')} />
}
