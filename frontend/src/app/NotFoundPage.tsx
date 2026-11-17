import { useTranslation } from 'react-i18next'

import { ErrorMessage } from './ErrorMessage'

export function NotFoundPage() {
  const { t } = useTranslation()
  return <ErrorMessage message={t('errors.notFound')} />
}
