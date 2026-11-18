import { useQuery } from '@tanstack/react-query'

import { api, call } from '@/api/client'

/** FR-INT-08: failing webhook deliveries and suspended subscriptions across clients. */
export function useWebhookHealth(enabled: boolean) {
  const clients = useQuery({
    queryKey: ['integration-clients'],
    queryFn: () => call(api.GET('/api/v1/integration-clients')),
    enabled,
    staleTime: 60_000,
  })
  const all = enabled ? (clients.data ?? []) : []
  return {
    failing: all.reduce((n, c) => n + c.webhooks.failing_deliveries, 0),
    suspended: all.reduce((n, c) => n + c.webhooks.suspended_subscriptions, 0),
  }
}
