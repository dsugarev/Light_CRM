import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, call, onApiRequest, type Schemas } from '@/api/client'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

import {
  ACTIVITY_KEY,
  idleSchedule,
  lastActivity,
  recordActivity,
  SIGNED_OUT_KEY,
} from './sessionActivity'
import { SESSION_EXPIRED_KEY } from './sessionExpiry'
import { ME_QUERY_KEY } from './useMe'

function minutesAndSeconds(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000))
  return `${String(Math.floor(total / 60))}:${String(total % 60).padStart(2, '0')}`
}

/**
 * FN-05: five minutes before the session times out for inactivity, ask whether to stay
 * signed in. Works across tabs: activity in any tab moves the deadline and closes the
 * dialog everywhere; signing out in one tab signs out all of them.
 */
export function IdleWarning({
  session,
  onSignOut,
}: {
  session: Schemas['SessionTimeouts']
  onSignOut: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  // Loading the app just made requests (at least GET /me), so now counts as activity;
  // a value left in storage by an earlier session must not end this one.
  const [activity, setActivity] = useState(() => Math.max(lastActivity() ?? 0, Date.now()))
  const [now, setNow] = useState(() => Date.now())
  const { deadline, warnAt } = idleSchedule(
    activity,
    session.idle_timeout_minutes,
    session.expires_at,
  )
  const warning = now >= warnAt && now < deadline

  // Every API request from this tab is activity, shared with the other tabs.
  useEffect(
    () =>
      onApiRequest(() => {
        const at = Date.now()
        recordActivity(at)
        setActivity(at)
      }),
    [],
  )

  // Other tabs: their activity, or their sign-out.
  useEffect(() => {
    const listen = (event: StorageEvent) => {
      if (event.key === ACTIVITY_KEY && event.newValue) {
        const at = Number(event.newValue)
        if (Number.isFinite(at)) setActivity((current) => Math.max(current, at))
      }
      if (event.key === SIGNED_OUT_KEY) {
        queryClient.setQueryData(SESSION_EXPIRED_KEY, false)
        queryClient.setQueryData(ME_QUERY_KEY, null)
      }
    }
    window.addEventListener('storage', listen)
    return () => {
      window.removeEventListener('storage', listen)
    }
  }, [queryClient])

  // Wake up at the warning time, then every second while the countdown runs.
  useEffect(() => {
    const delay = warning ? 1000 : Math.max(0, Math.min(warnAt, deadline) - Date.now())
    const timer = setTimeout(() => {
      setNow(Date.now())
    }, delay)
    return () => {
      clearTimeout(timer)
    }
  }, [warning, warnAt, deadline, now])

  // The deadline passed without activity: end the session here too, and say so (FN-04).
  useEffect(() => {
    if (now < deadline) return
    void call(api.POST('/api/v1/auth/logout'))
      .catch(() => undefined)
      .finally(() => {
        queryClient.setQueryData(SESSION_EXPIRED_KEY, true)
        queryClient.setQueryData(ME_QUERY_KEY, null)
      })
  }, [now, deadline, queryClient])

  return (
    <AlertDialog open={warning}>
      <AlertDialogContent>
        <AlertDialogTitle>{t('idle.title')}</AlertDialogTitle>
        <AlertDialogDescription>
          {t('idle.text', { time: minutesAndSeconds(deadline - now) })}
        </AlertDialogDescription>
        <AlertDialogFooter>
          <AlertDialogCancel variant="outline" onClick={onSignOut}>
            {t('nav.signOut')}
          </AlertDialogCancel>
          <AlertDialogCancel
            variant="default"
            onClick={() => {
              // Any request is activity: this one also refreshes the profile.
              void call(api.GET('/api/v1/me')).then((me) => {
                queryClient.setQueryData(ME_QUERY_KEY, me)
              })
            }}
          >
            {t('idle.stay')}
          </AlertDialogCancel>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
