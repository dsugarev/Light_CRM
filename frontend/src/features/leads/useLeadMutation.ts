import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { ApiError } from '@/api/client'
import { useErrorText } from '@/lib/errors'

import type { Lead } from './leadValues'

/**
 * A change to a lead. On success the cached lead is replaced. On a version
 * conflict the server's current lead (409 `current`) is shown and the user is
 * asked to repeat the change; other errors become a translated toast.
 */
export function useLeadMutation<V>(
  leadId: string,
  mutationFn: (variables: V) => Promise<Lead>,
  successMessage: (lead: Lead) => string,
) {
  const queryClient = useQueryClient()
  const { t } = useTranslation('leads')
  const errorText = useErrorText()
  return useMutation({
    mutationFn,
    onSuccess: async (lead) => {
      queryClient.setQueryData(['leads', leadId], lead)
      await queryClient.invalidateQueries({ queryKey: ['leads'], refetchType: 'none' })
      await queryClient.invalidateQueries({ queryKey: ['organizations'] })
      toast.success(successMessage(lead))
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'conflict.version_mismatch') {
        queryClient.setQueryData(['leads', leadId], error.problem['current'])
        toast.error(t('toasts.conflict'))
        return
      }
      if (!(error instanceof ApiError && error.errors.length > 0)) {
        toast.error(errorText(error instanceof ApiError ? error.code : undefined))
      }
    },
  })
}
