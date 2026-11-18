import { toast } from 'sonner'

import { ApiError } from '@/api/client'

import { useErrorText } from './errors'

/**
 * UX-05: the one way to tell the user how an action went. Errors are mapped from the
 * backend's problem `code` to a translated message, with a generic fallback for unknown
 * codes and network failures; never raw error text.
 */
export function useNotify() {
  const errorText = useErrorText()
  return {
    success: (message: string) => {
      toast.success(message)
    },
    /** `message` replaces the mapped text when the caller knows better (a version conflict). */
    error: (error: unknown, message?: string) => {
      toast.error(message ?? errorText(error instanceof ApiError ? error.code : undefined))
    },
    /** A non-blocking warning from the API, by its code. */
    warning: (code: string) => {
      toast.warning(errorText(code))
    },
  }
}
