import { useQuery } from '@tanstack/react-query'

import { api, call, type Schemas } from '@/api/client'

/**
 * FN-08: whether a user is the last active Admin, so the UI can disable demoting or
 * deactivating them (the backend refuses with 409 permission.last_admin anyway).
 */
export function useLastAdmin() {
  const admins = useQuery({
    queryKey: ['users', 'active-admins'],
    queryFn: () =>
      call(
        api.GET('/api/v1/users', {
          params: { query: { role: 'admin', is_active: true, page_size: 1 } },
        }),
      ),
  })
  return (user: Schemas['UserOut']) =>
    user.role === 'admin' && user.is_active && admins.data !== undefined && admins.data.total <= 1
}
