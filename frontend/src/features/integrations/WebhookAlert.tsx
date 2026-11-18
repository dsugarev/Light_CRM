import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

/** The alert shown in the admin area while deliveries are failing. */
export function WebhookAlert({ failing, suspended }: { failing: number; suspended: number }) {
  const { t } = useTranslation('integrations')
  if (failing === 0 && suspended === 0) return null
  return (
    <Alert variant="destructive" className="mb-4">
      <AlertTitle>{t('alert.title')}</AlertTitle>
      <AlertDescription>
        <span>
          {t('alert.text', { failing, suspended })}{' '}
          <Link to="/admin/integrations/deliveries?status=retrying" className="underline">
            {t('alert.link')}
          </Link>
        </span>
      </AlertDescription>
    </Alert>
  )
}
