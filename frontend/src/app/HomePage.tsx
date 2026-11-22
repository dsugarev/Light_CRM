import { useTranslation } from 'react-i18next'

import { PageHeader } from '@/components/PageHeader'
import { useMe } from '@/features/auth/useMe'
import { RecentlyViewed } from '@/features/recent/RecentlyViewed'
import { Dashboard } from '@/features/reports/Dashboard'

export function HomePage() {
  const { t } = useTranslation()
  const { data: me } = useMe()
  return (
    <section className="mx-auto flex max-w-7xl flex-col gap-6">
      <PageHeader title={t('home.title', { name: me?.full_name ?? '' })} />
      <RecentlyViewed />
      <Dashboard />
    </section>
  )
}
