import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { SUPPORTED_LOCALES } from '@/i18n'

import { useChangeLocale } from './useChangeLocale'

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation()
  const change = useChangeLocale()

  return (
    <div role="group" aria-label={t('language.label')} className="flex gap-1">
      {SUPPORTED_LOCALES.map((locale) => (
        <Button
          key={locale}
          type="button"
          size="sm"
          variant={i18n.resolvedLanguage === locale ? 'secondary' : 'ghost'}
          aria-pressed={i18n.resolvedLanguage === locale}
          lang={locale}
          onClick={() => {
            change(locale)
          }}
        >
          {t(`language.${locale}`)}
        </Button>
      ))}
    </div>
  )
}
