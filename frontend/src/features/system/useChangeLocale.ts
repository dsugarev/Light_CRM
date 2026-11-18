import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { api, call } from '@/api/client'
import { ME_QUERY_KEY, useMe } from '@/features/auth/useMe'
import { type Locale } from '@/i18n'
import { storeLocale } from '@/lib/locale'

/** FR-I18N-01: signed-in users keep the choice on their profile; others in the browser. */
export function useChangeLocale() {
  const { i18n } = useTranslation()
  const { data: me } = useMe()
  const queryClient = useQueryClient()
  const saveLocale = useMutation({
    mutationFn: (locale: Locale) => call(api.PATCH('/api/v1/me', { body: { locale } })),
    onSuccess: (updated) => {
      queryClient.setQueryData(ME_QUERY_KEY, updated)
    },
  })

  return (locale: Locale) => {
    storeLocale(locale)
    void i18n.changeLanguage(locale)
    if (me) saveLocale.mutate(locale)
  }
}
