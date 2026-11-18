import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'
import { useNotify } from '@/lib/notify'

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
  const notify = useNotify()
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['timeline'] }),
        queryClient.invalidateQueries({ queryKey: ['tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['opportunities'] }),
      ])
      notify.success(successMessage)
    },
    onError: async (error) => {
      if (error instanceof ApiError && error.code === 'conflict.version_mismatch') {
        await queryClient.invalidateQueries({ queryKey: ['timeline'] })
        await queryClient.invalidateQueries({ queryKey: ['tasks'] })
        notify.error(error, t('toasts.conflict'))
        return
      }
      if (toastFieldErrors || !(error instanceof ApiError && error.errors.length > 0)) {
        notify.error(error)
      }
    },
  })
}
