import { useId, type ReactElement, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Label } from '@/components/ui/label'
import { useErrorText } from '@/lib/errors'

interface FieldControlProps {
  id: string
  'aria-invalid': boolean
  'aria-describedby'?: string
  'aria-required'?: true
}

interface FormFieldProps {
  label: string
  /** Error code (field or problem code), translated for display. */
  error?: string | undefined
  hint?: ReactNode
  /** UX-11: shows a required marker and sets aria-required on the control. */
  required?: boolean
  children: (control: FieldControlProps) => ReactElement
}

/**
 * The one form field layout (UX-11): label (with a required marker), the control, then
 * an inline error translated from the backend's field code, or a hint; consistent spacing.
 * The control gets its id, aria-invalid, aria-describedby and aria-required from here.
 */
export function FormField({ label, error, hint, required = false, children }: FormFieldProps) {
  const id = useId()
  const { t } = useTranslation()
  const errorText = useErrorText()
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline gap-1">
        <Label htmlFor={id}>{label}</Label>
        {/* Outside the label so its text stays the field's name; aria-required tells
            assistive technology, the title tells pointer users. */}
        {required ? (
          <span
            aria-hidden="true"
            title={t('form.required')}
            className="text-sm leading-none text-destructive"
          >
            *
          </span>
        ) : null}
      </div>
      {children({
        id,
        'aria-invalid': Boolean(error),
        ...(describedBy ? { 'aria-describedby': describedBy } : {}),
        ...(required ? { 'aria-required': true as const } : {}),
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
