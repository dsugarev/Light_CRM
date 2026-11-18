/** Set by the query client when a 401 ends a signed-in session (FN-04). */
export const SESSION_EXPIRED_KEY = ['session-expired'] as const

/**
 * FN-04: where a 401 sends the user. Back to sign-in, saying the session ended when they
 * were signed in, and returning them to the page they were on after signing in again.
 */
export function signInAfterUnauthorized(
  location: { pathname: string; search: string },
  sessionExpired: boolean,
): string {
  if (location.pathname === '/sign-in') return `/sign-in${location.search}`
  const params = new URLSearchParams({ next: location.pathname + location.search })
  if (sessionExpired) params.set('expired', '1')
  return `/sign-in?${params.toString()}`
}
