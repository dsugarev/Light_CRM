import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, Outlet, useLocation } from 'react-router'

import { Loading } from '@/components/Loading'
import { isLocale } from '@/i18n'
import { storeLocale } from '@/lib/locale'
import { useCan } from '@/lib/permissions'

import { useMe } from './useMe'

/** Routes below need a signed-in user; the UI follows the profile language. */
export function RequireAuth() {
  const { data: me, isPending } = useMe()
  const { i18n } = useTranslation()
  const location = useLocation()

  useEffect(() => {
    if (me && isLocale(me.locale) && me.locale !== i18n.resolvedLanguage) {
      storeLocale(me.locale)
      void i18n.changeLanguage(me.locale)
    }
  }, [me, i18n])

  if (isPending) return <Loading />
  if (!me) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/sign-in?next=${next}`} replace />
  }
  return <Outlet />
}

/** UI-only guard: hides admin pages from users without the permission. */
export function RequirePermission({ permission }: { permission: string }) {
  const can = useCan()
  return can(permission) ? <Outlet /> : <Navigate to="/" replace />
}
