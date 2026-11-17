import { useMe } from '@/features/auth/useMe'

/**
 * UI convenience mirroring the server's permission list (GET /me). It only hides
 * controls; the server remains the authority (FR-AUTH-05).
 */
export function useCan() {
  const { data: me } = useMe()
  const granted = new Set(me?.permissions ?? [])
  return (permission: string) => granted.has(permission)
}
