import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { api, call } from '@/api/client'
import { Button } from '@/components/ui/button'
import { ME_QUERY_KEY, useMe } from '@/features/auth/useMe'
import { SUPPORTED_LOCALES, type Locale } from '@/i18n'
import { storeLocale } from '@/lib/locale'

/** FR-I18N-01: signed-in users keep the choice on their profile; others in the browser. */
export function LanguageSwitcher() {
  const { t, i18n } = useTranslation()
  const { data: me } = useMe()
  const queryClient = useQueryClient()
  const saveLocale = useMutation({
    mutationFn: (locale: Locale) => call(api.PATCH('/api/v1/me', { body: { locale } })),
    onSuccess: (updated) => {
      queryClient.setQueryData(ME_QUERY_KEY, updated)
    },
  })

  const change = (locale: Locale) => {
    storeLocale(locale)
    void i18n.changeLanguage(locale)
    if (me) saveLocale.mutate(locale)
  }

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
