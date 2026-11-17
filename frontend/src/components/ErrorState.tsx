import { ApiError } from '@/api/client'
import { FormMessage } from '@/components/FormMessage'

/** Translated message for a failed query (never raw error details). */
export function ErrorState({ error }: { error: unknown }) {
  return <FormMessage error={error instanceof ApiError ? error.code : 'unknown'} />
}
