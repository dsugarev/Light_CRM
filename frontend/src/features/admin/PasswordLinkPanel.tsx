import { useTranslation } from 'react-i18next'

import type { Schemas } from '@/api/client'
import { CopyField } from '@/components/CopyField'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

/** FR-AUTH-02: the one-time link is shown to the Admin (and emailed when SMTP is set). */
export function PasswordLinkPanel({ link, name }: { link: Schemas['PasswordLink']; name: string }) {
  const { t } = useTranslation('admin')
  const locale = useLocale()
  return (
    <Alert role="status" data-testid="password-link">
      <AlertTitle>{t('link.title')}</AlertTitle>
      <AlertDescription className="flex flex-col gap-3">
        <span>{t('link.explain', { name, expires: formatDateTime(link.expires_at, locale) })}</span>
        <CopyField value={link.url} label={t('link.title')} />
        <span>{link.emailed ? t('link.emailed') : t('link.notEmailed')}</span>
      </AlertDescription>
    </Alert>
  )
}
