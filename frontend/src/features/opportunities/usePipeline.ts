import { useQuery } from '@tanstack/react-query'

import { api, call } from '@/api/client'

/** The default pipeline with all its stages, in order (one pipeline in R1). */
export function usePipeline() {
  return useQuery({
    queryKey: ['pipelines'],
    queryFn: () => call(api.GET('/api/v1/pipelines')),
    select: (pipelines) => pipelines.find((p) => p.is_default) ?? pipelines[0],
    staleTime: 5 * 60_000,
  })
}
