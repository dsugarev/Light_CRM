import { useEffect, useSyncExternalStore } from 'react'

import { ApiError } from '@/api/client'
import { useMe } from '@/features/auth/useMe'

import {
  CHANGED_EVENT,
  forgetRecent,
  readRecent,
  rememberRecent,
  type RecentRecord,
  type RecordType,
} from './recentRecords'

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGED_EVENT, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(CHANGED_EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

/** The signed-in user's recently viewed records, kept current across tabs. */
export function useRecentRecords(): RecentRecord[] {
  const { data: me } = useMe()
  // The snapshot must be stable between changes, so it is the raw stored string.
  const raw = useSyncExternalStore(subscribe, () => (me ? JSON.stringify(readRecent(me.id)) : '[]'))
  return JSON.parse(raw) as RecentRecord[]
}

/**
 * Called by a record page: remembers the record once it has loaded, and forgets it when
 * it no longer exists (404), so the list never leads to an error page twice.
 */
export function useTrackRecent(
  type: RecordType,
  id: string,
  label: string | undefined,
  error: unknown,
) {
  const { data: me } = useMe()
  const userId = me?.id
  useEffect(() => {
    if (userId && label) rememberRecent(userId, { type, id, label })
  }, [userId, type, id, label])
  const missing = error instanceof ApiError && error.status === 404
  useEffect(() => {
    if (userId && missing) forgetRecent(userId, type, id)
  }, [userId, type, id, missing])
}
