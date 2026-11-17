import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import { ApiError } from '@/api/client'
import { useErrorText } from '@/lib/errors'

/**
 * A change to activities. Timelines, task lists and opportunities (their
 * "needs attention" flag depends on activity) refresh afterwards.
 */
export function useActivityMutation<V, R>(
  mutationFn: (variables: V) => Promise<R>,
  successMessage: string,
  { toastFieldErrors = true }: { toastFieldErrors?: boolean } = {},
) {
  const queryClient = useQueryClient()
  const { t } = useTranslation('activities')
  const errorText = useErrorText()
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['timeline'] }),
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['opportunities'] }),
      ])
      toast.success(successMessage)
    },
    onError: async (error) => {
      if (error instanceof ApiError && error.code === 'conflict.version_mismatch') {
        await queryClient.invalidateQueries({ queryKey: ['timeline'] })
        await queryClient.invalidateQueries({ queryKey: ['tasks'] })
        toast.error(t('toasts.conflict'))
        return
      }
      if (toastFieldErrors || !(error instanceof ApiError && error.errors.length > 0)) {
        toast.error(errorText(error instanceof ApiError ? error.code : undefined))
      }
    },
  })
}
