import { useTranslation } from 'react-i18next'

export function Loading() {
  const { t } = useTranslation()
  return (
    <p role="status" className="py-8 text-center text-sm text-muted-foreground">
      {t('states.loading')}
    </p>
  )
}
