import { useQuery } from '@tanstack/react-query'

import { api, call } from '@/api/client'

/** Active people for owner pickers (GET /users/lookup). */
export function useUserLookup(enabled: boolean) {
  return useQuery({
    queryKey: ['users', 'lookup'],
    queryFn: () => call(api.GET('/api/v1/users/lookup', { params: { query: { page_size: 100 } } })),
    enabled,
    staleTime: 60_000,
  })
}
