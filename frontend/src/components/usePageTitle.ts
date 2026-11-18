import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * The browser tab says which page this is: "Leads · Light CRM" (WCAG 2.4.2 Page Titled;
 * several CRM tabs stay apart). PageHeader, AuthCard and the error page call it.
 */
export function usePageTitle(title: string) {
  const { t } = useTranslation()
  const app = t('app.name')
  useEffect(() => {
    document.title = title && title !== app ? `${title} · ${app}` : app
  }, [title, app])
}
