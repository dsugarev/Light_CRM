import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'

export type ApiHealth = 'ok' | 'unavailable'

export function useApiHealth() {
  return useQuery({
    queryKey: ['system', 'health', 'ready'],
    queryFn: async ({ signal }): Promise<ApiHealth> => {
      try {
        const { data } = await api.GET('/api/health/ready', { signal })
        return data?.status === 'ok' ? 'ok' : 'unavailable'
      } catch {
        return 'unavailable'
      }
    },
    refetchInterval: 30_000,
    retry: false,
  })
}
