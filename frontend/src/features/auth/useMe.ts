import { useQuery, useQueryClient } from '@tanstack/react-query'

import { api, call, isUnauthorized, type Schemas } from '@/api/client'

import { SESSION_EXPIRED_KEY } from './sessionExpiry'

export type Me = Schemas['Me']

export const ME_QUERY_KEY = ['me'] as const

/** The signed-in user, or null when nobody is signed in. */
export function useMe() {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await call(api.GET('/api/v1/me'))
      } catch (error) {
        if (isUnauthorized(error)) {
          // FN-04: when this reload is the first request after the session ended, it is
          // the one that must record it, or sign-in would not say why.
          const previous: unknown = queryClient.getQueryData(ME_QUERY_KEY)
          if (previous != null) queryClient.setQueryData(SESSION_EXPIRED_KEY, true)
          return null
        }
        throw error
      }
    },
    staleTime: 5 * 60_000,
  })
}
