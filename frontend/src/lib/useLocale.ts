import { useTranslation } from 'react-i18next'

import { isLocale, type Locale } from '@/i18n'

export function useLocale(): Locale {
  const { i18n } = useTranslation()
  const current = i18n.resolvedLanguage
  return isLocale(current) ? current : 'en'
}
