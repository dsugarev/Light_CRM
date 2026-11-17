import { useQuery } from '@tanstack/react-query'

import { api, call, isUnauthorized, type Schemas } from '@/api/client'

export type Me = Schemas['Me']

export const ME_QUERY_KEY = ['me'] as const

/** The signed-in user, or null when nobody is signed in. */
export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await call(api.GET('/api/v1/me'))
      } catch (error) {
        if (isUnauthorized(error)) return null
        throw error
      }
    },
    staleTime: 5 * 60_000,
  })
}
