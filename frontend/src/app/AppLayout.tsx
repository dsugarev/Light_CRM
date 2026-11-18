import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Dialog } from '@base-ui/react/dialog'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { Toaster } from 'sonner'

import { api, call } from '@/api/client'
import { Button, buttonVariants } from '@/components/ui/button'
import { AssistantLauncher } from '@/features/assistant/AssistantLauncher'
import { ME_QUERY_KEY, useMe } from '@/features/auth/useMe'
import { useWebhookHealth } from '@/features/integrations/useWebhookHealth'
import { WebhookAlert } from '@/features/integrations/WebhookAlert'
import { HeaderSearch } from '@/features/search/HeaderSearch'
import { ApiStatus } from '@/features/system/ApiStatus'
import { LanguageSwitcher } from '@/features/system/LanguageSwitcher'
import { useCan } from '@/lib/permissions'

import { AppNav } from './AppNav'
import { UserMenu } from './UserMenu'
import { useSidebarCollapsed } from './useSidebarCollapsed'

export function AppLayout() {
  const { t, i18n } = useTranslation()
  const { data: me } = useMe()
  const can = useCan()
  const show = { users: can('users.manage') }
  const [collapsed, setCollapsed] = useSidebarCollapsed()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const webhookHealth = useWebhookHealth(show.users)
  const webhookProblems = webhookHealth.failing + webhookHealth.suspended
  const inAdminArea = useLocation().pathname.startsWith('/admin')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const signOut = useMutation({
    mutationFn: () => call(api.POST('/api/v1/auth/logout')),
    onSettled: async () => {
      queryClient.setQueryData(ME_QUERY_KEY, null)
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== ME_QUERY_KEY[0] })
      await navigate('/sign-in', { replace: true })
    },
  })

  useEffect(() => {
    document.documentElement.lang = i18n.resolvedLanguage ?? 'en'
    document.title = t('app.name')
  }, [i18n.resolvedLanguage, t])

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      {/* WCAG 2.4.1: keyboard users skip the navigation. Visible when focused. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:shadow"
      >
        {t('nav.skipToContent')}
      </a>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2 lg:px-6">
        <div className="flex items-center gap-2">
          {me ? (
            <>
              {/* UX-02: below 1024 px the navigation opens as a drawer. */}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="lg:hidden"
                aria-haspopup="dialog"
                onClick={() => {
                  setDrawerOpen(true)
                }}
              >
                {t('nav.menu')}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="hidden lg:inline-flex"
                aria-expanded={!collapsed}
                aria-controls="app-sidebar"
                onClick={() => {
                  setCollapsed(!collapsed)
                }}
              >
                {collapsed ? t('nav.show') : t('nav.hide')}
              </Button>
            </>
          ) : null}
          <NavLink to="/" className="px-2 font-semibold">
            {t('app.name')}
          </NavLink>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {me ? <HeaderSearch /> : null}
          {me ? <AssistantLauncher /> : null}
          {me ? (
            <UserMenu
              fullName={me.full_name}
              onSignOut={() => {
                signOut.mutate()
              }}
            />
          ) : (
            <LanguageSwitcher />
          )}
        </div>
      </header>
      <div className="flex flex-1">
        {me ? (
          <div
            id="app-sidebar"
            className={`w-56 shrink-0 border-r px-2 py-4 ${collapsed ? 'hidden' : 'hidden lg:block'}`}
          >
            <AppNav webhookProblems={webhookProblems} />
          </div>
        ) : null}
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 px-4 py-6 outline-none lg:px-6">
          {show.users && inAdminArea ? <WebhookAlert {...webhookHealth} /> : null}
          <Outlet />
        </main>
      </div>
      {me ? (
        <Dialog.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
          <Dialog.Portal>
            <Dialog.Backdrop className="fixed inset-0 z-40 bg-overlay/20" />
            <Dialog.Popup className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col gap-4 overflow-y-auto bg-background p-4 shadow-lg outline-none">
              <div className="flex items-center justify-between">
                <Dialog.Title className="font-semibold">{t('app.name')}</Dialog.Title>
                <Dialog.Close className={buttonVariants({ variant: 'ghost', size: 'sm' })}>
                  {t('nav.close')}
                </Dialog.Close>
              </div>
              <AppNav
                webhookProblems={webhookProblems}
                onNavigate={() => {
                  setDrawerOpen(false)
                }}
              />
            </Dialog.Popup>
          </Dialog.Portal>
        </Dialog.Root>
      ) : null}
      <Toaster position="bottom-right" richColors closeButton />
      <footer className="border-t px-4 py-2 lg:px-6">
        <ApiStatus />
      </footer>
    </div>
  )
}
