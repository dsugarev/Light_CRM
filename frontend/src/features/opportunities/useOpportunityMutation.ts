import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'
import { useNotify } from '@/lib/notify'

import type { Opportunity } from './opportunityValues'

/**
 * A change to an opportunity. On success the cached opportunity is replaced and
 * lists, the board and organization counts refresh. On a version conflict the
 * server's current opportunity (409 `current`) is shown; other errors become a
 * translated toast unless the caller handles field errors.
 */
export function useOpportunityMutation<V>(
  opportunityId: string,
  mutationFn: (variables: V) => Promise<Opportunity>,
  successMessage: (opportunity: Opportunity) => string,
) {
  const queryClient = useQueryClient()
  const { t } = useTranslation('opportunities')
  const notify = useNotify()
  return useMutation({
    mutationFn,
    onSuccess: async (opportunity) => {
      queryClient.setQueryData(['opportunities', opportunityId], opportunity)
      await queryClient.invalidateQueries({ queryKey: ['opportunities'], refetchType: 'active' })
      await queryClient.invalidateQueries({ queryKey: ['organizations'] })
      notify.success(successMessage(opportunity))
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'conflict.version_mismatch') {
        queryClient.setQueryData(['opportunities', opportunityId], error.problem['current'])
        notify.error(error, t('toasts.conflict'))
        return
      }
      if (!(error instanceof ApiError && error.errors.length > 0)) {
        notify.error(error)
      }
    },
  })
}
