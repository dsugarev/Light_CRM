import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

import { isUnauthorized } from '@/api/client'

import { ME_QUERY_KEY } from '@/features/auth/useMe'

/**
 * A 401 from any request means the session ended (sign-out elsewhere, timeout,
 * deactivation): forget the current user and let the router send them to sign-in.
 */
export function createQueryClient(onUnauthorized: () => void = () => undefined) {
  const handle = (error: unknown) => {
    if (isUnauthorized(error)) {
      queryClient.setQueryData(ME_QUERY_KEY, null)
      onUnauthorized()
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
