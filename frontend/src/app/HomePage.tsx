import { useTranslation } from 'react-i18next'

import { useMe } from '@/features/auth/useMe'
import { Dashboard } from '@/features/reports/Dashboard'

export function HomePage() {
  const { t } = useTranslation()
  const { data: me } = useMe()
  return (
    <section className="mx-auto flex max-w-7xl flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t('home.title', { name: me?.full_name ?? '' })}</h1>
      <Dashboard />
    </section>
  )
}
