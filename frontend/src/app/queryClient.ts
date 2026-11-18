import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

import { isUnauthorized } from '@/api/client'

import { SESSION_EXPIRED_KEY } from '@/features/auth/sessionExpiry'
import { ME_QUERY_KEY } from '@/features/auth/useMe'

/**
 * A 401 from any request means the session ended (sign-out elsewhere, timeout,
 * deactivation): forget the current user and let the router send them to sign-in.
 */
export function createQueryClient() {
  const handle = (error: unknown) => {
    if (isUnauthorized(error)) {
      // FN-04: someone who was signed in lost their session; a first visit did not.
      // RequireAuth then sends them to sign-in, with the message and the way back.
      const previous: unknown = queryClient.getQueryData(ME_QUERY_KEY)
      queryClient.setQueryData(SESSION_EXPIRED_KEY, previous != null)
      queryClient.setQueryData(ME_QUERY_KEY, null)
    }
  }
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError: handle }),
    mutationCache: new MutationCache({
      onError: handle,
      // Any change can add an event to record timelines (FR-ACT-03); mark them stale.
      onSuccess: () => queryClient.invalidateQueries({ queryKey: ['timeline'] }),
    }),
    defaultOptions: {
      queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: false },
    },
  })
  return queryClient
}
