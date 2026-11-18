/**
 * Recently viewed records (CRM best practice: get back to what you were working on).
 * Kept per user in this browser only, at most MAX entries, newest first; cleared on
 * sign-out so a shared computer does not show the previous user's records.
 */
export type RecordType = 'organization' | 'contact' | 'lead' | 'opportunity'

export interface RecentRecord {
  type: RecordType
  id: string
  label: string
  /** When it was last opened (ms since the epoch). */
  at: number
}

export const MAX_RECENT = 8
const PREFIX = 'crm.recent.'
export const CHANGED_EVENT = 'crm-recent-changed'

const keyFor = (userId: string) => `${PREFIX}${userId}`

export function readRecent(userId: string): RecentRecord[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(keyFor(userId)) ?? '[]')
    return Array.isArray(parsed) ? (parsed as RecentRecord[]) : []
  } catch {
    return []
  }
}

function write(userId: string, records: RecentRecord[]) {
  try {
    localStorage.setItem(keyFor(userId), JSON.stringify(records))
    // Same-tab listeners; other tabs get the storage event.
    window.dispatchEvent(new Event(CHANGED_EVENT))
  } catch {
    // Storage blocked: the list simply stays empty.
  }
}

export function rememberRecent(userId: string, record: Omit<RecentRecord, 'at'>, at = Date.now()) {
  const others = readRecent(userId).filter((r) => !(r.type === record.type && r.id === record.id))
  write(userId, [{ ...record, at }, ...others].slice(0, MAX_RECENT))
}

export function forgetRecent(userId: string, type: RecordType, id: string) {
  const records = readRecent(userId)
  const kept = records.filter((r) => !(r.type === type && r.id === id))
  if (kept.length !== records.length) write(userId, kept)
}

/** On sign-out: no user's recent records stay in this browser. */
export function clearAllRecent() {
  try {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith(PREFIX)) localStorage.removeItem(key)
    }
    window.dispatchEvent(new Event(CHANGED_EVENT))
  } catch {
    // Nothing stored.
  }
}
