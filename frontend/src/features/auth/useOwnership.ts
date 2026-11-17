import { useMe } from '@/features/auth/useMe'
import { useCan } from '@/lib/permissions'

/** UI mirror of the Owner+ rule: Managers/Admins edit anything, Reps their own records. */
export function useCanEditOwned() {
  const { data: me } = useMe()
  const can = useCan()
  return (ownerId: string | undefined) =>
    can('records.edit_any') ||
    (can('records.edit_own') && ownerId !== undefined && ownerId === me?.id)
}
