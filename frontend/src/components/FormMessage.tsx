import { Alert, AlertDescription } from '@/components/ui/alert'
import { useErrorText } from '@/lib/errors'

/** Form-level message: an error code to translate, or a ready success text. */
export function FormMessage({
  error,
  success,
  values,
}: {
  error?: string | null | undefined
  success?: string | null | undefined
  values?: Record<string, string>
}) {
  const errorText = useErrorText()
  if (error) {
    return (
      <Alert variant="destructive" role="alert">
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
