import { useEffect, useRef } from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { useErrorText } from '@/lib/errors'

/**
 * Form-level message: an error code to translate, or a ready success text.
 * `focusOnError` (UX-06) moves focus to a new error so keyboard and screen-reader
 * users land on it.
 */
export function FormMessage({
  error,
  success,
  values,
  focusOnError = false,
}: {
  error?: string | null | undefined
  success?: string | null | undefined
  values?: Record<string, string>
  focusOnError?: boolean
}) {
  const errorText = useErrorText()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (focusOnError && error) ref.current?.focus()
  }, [focusOnError, error])
  if (error) {
    return (
      <Alert ref={ref} tabIndex={-1} variant="destructive" role="alert" className="outline-none">
        <AlertDescription>{errorText(error, values)}</AlertDescription>
      </Alert>
    )
  }
  if (success) {
    return (
      <Alert role="status">
        <AlertDescription>{success}</AlertDescription>
      </Alert>
    )
  }
  return null
}
