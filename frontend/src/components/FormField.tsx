import { useId, type ReactElement, type ReactNode } from 'react'

import { Label } from '@/components/ui/label'
import { useErrorText } from '@/lib/errors'

interface FieldControlProps {
  id: string
  'aria-invalid': boolean
  'aria-describedby'?: string
}

interface FormFieldProps {
  label: string
  /** Error code (field or problem code), translated for display. */
  error?: string | undefined
  hint?: ReactNode
  children: (control: FieldControlProps) => ReactElement
}

/** Label, control and an accessible error/hint, wired with ids. */
export function FormField({ label, error, hint, children }: FormFieldProps) {
  const id = useId()
  const errorText = useErrorText()
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      {children({
        id,
        'aria-invalid': Boolean(error),
        ...(describedBy ? { 'aria-describedby': describedBy } : {}),
      })}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-destructive">
          {errorText(error)}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
