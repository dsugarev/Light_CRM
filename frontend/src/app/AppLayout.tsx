import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet } from 'react-router'

import { ApiStatus } from '@/features/system/ApiStatus'
import { LanguageSwitcher } from '@/features/system/LanguageSwitcher'

export function AppLayout() {
  const { t, i18n } = useTranslation()

  useEffect(() => {
    document.documentElement.lang = i18n.resolvedLanguage ?? 'en'
    document.title = t('app.name')
  }, [i18n.resolvedLanguage, t])

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <span className="font-semibold">{t('app.name')}</span>
        <LanguageSwitcher />
      </header>
      <main className="flex-1 px-6">
        <Outlet />
      </main>
      <footer className="border-t px-6 py-2">
        <ApiStatus />
      </footer>
    </div>
  )
}
