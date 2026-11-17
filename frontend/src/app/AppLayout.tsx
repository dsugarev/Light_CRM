import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useNavigate } from 'react-router'

import { api, call } from '@/api/client'
import { Button } from '@/components/ui/button'
import { ME_QUERY_KEY, useMe } from '@/features/auth/useMe'
import { ApiStatus } from '@/features/system/ApiStatus'
import { LanguageSwitcher } from '@/features/system/LanguageSwitcher'
import { useCan } from '@/lib/permissions'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-2 py-1 text-sm ${isActive ? 'bg-secondary font-medium' : 'hover:bg-muted'}`

export function AppLayout() {
  const { t, i18n } = useTranslation()
  const { data: me } = useMe()
  const can = useCan()
  const show = {
    users: can('users.manage'),
    audit: can('audit.read'),
    settings: can('settings.manage'),
  }
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
      <header className="flex flex-wrap items-center justify-between gap-4 border-b px-6 py-3">
        <div className="flex items-center gap-6">
          <NavLink to="/" className="font-semibold">
            {t('app.name')}
          </NavLink>
          {me ? (
            <nav aria-label={t('nav.label')} className="flex flex-wrap gap-1">
              <NavLink to="/" end className={linkClass}>
                {t('nav.home')}
              </NavLink>
              {show.users ? (
                <NavLink to="/admin/users" className={linkClass}>
                  {t('nav.users')}
                </NavLink>
              ) : null}
              {show.audit ? (
                <NavLink to="/admin/audit-log" className={linkClass}>
                  {t('nav.auditLog')}
                </NavLink>
              ) : null}
              {show.settings ? (
                <NavLink to="/admin/settings" className={linkClass}>
                  {t('nav.settings')}
                </NavLink>
              ) : null}
            </nav>
          ) : null}
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          {me ? (
            <>
              <NavLink to="/profile" className={linkClass} title={t('nav.profile')}>
                {me.full_name}
              </NavLink>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  signOut.mutate()
                }}
              >
                {t('nav.signOut')}
              </Button>
            </>
          ) : null}
        </div>
      </header>
      <main className="flex-1 px-6 py-6">
        <Outlet />
      </main>
      <footer className="border-t px-6 py-2">
        <ApiStatus />
      </footer>
    </div>
  )
}
