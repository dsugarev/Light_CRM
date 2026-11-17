import { useTranslation } from 'react-i18next'

import { useMe } from '@/features/auth/useMe'

export function HomePage() {
  const { t } = useTranslation()
  const { data: me } = useMe()
  return (
    <section className="mx-auto max-w-3xl">
      <h1 className="mb-2 text-2xl font-semibold">
        {t('home.title', { name: me?.full_name ?? '' })}
      </h1>
      <p className="text-muted-foreground">{t('home.intro')}</p>
    </section>
  )
}
