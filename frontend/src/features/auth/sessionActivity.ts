/**
 * FN-05: when the session will time out for inactivity, shared by every open tab.
 * Each API request stores its time in localStorage; other tabs learn of it from the
 * `storage` event. The server records activity at most once a minute (API spec section 4,
 * `GET /me` `session`), so the idle time is counted from a minute before the last request.
 */
export const ACTIVITY_KEY = 'crm.activity'
export const SIGNED_OUT_KEY = 'crm.signed-out'
export const WARN_BEFORE_MS = 5 * 60_000
const SERVER_TOUCH_MS = 60_000

function read(key: string): number | null {
  try {
    const value = Number(localStorage.getItem(key))
    return Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

function write(key: string, value: number) {
  try {
    localStorage.setItem(key, String(value))
  } catch {
    // Storage blocked: this tab still warns on its own activity.
  }
}

export function recordActivity(now = Date.now()) {
  write(ACTIVITY_KEY, now)
}

export function lastActivity(): number | null {
  return read(ACTIVITY_KEY)
}

/** Tell the other tabs that this one signed out. */
export function broadcastSignOut(now = Date.now()) {
  write(SIGNED_OUT_KEY, now)
}

export interface IdleSchedule {
  /** When the session ends: idle timeout or absolute expiry, whichever comes first. */
  deadline: number
  /** When to show the warning. */
  warnAt: number
}

export function idleSchedule(
  lastActivityAt: number,
  idleTimeoutMinutes: number,
  expiresAt: string,
): IdleSchedule {
  const idleEnd = lastActivityAt - SERVER_TOUCH_MS + idleTimeoutMinutes * 60_000
  const deadline = Math.min(idleEnd, new Date(expiresAt).getTime())
  return { deadline, warnAt: deadline - WARN_BEFORE_MS }
}
