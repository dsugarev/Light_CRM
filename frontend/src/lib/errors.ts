import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'

/** Translate an error code (API problem code or field code) to a message. */
export function useErrorText() {
  const { i18n } = useTranslation('errors')
  // Codes come from the server at runtime, so the typed key union cannot apply;
  // existence is checked first and unknown codes fall back to a generic message.
  // Translated when called, so a toast raised after a language switch uses the new language.
  const translate = i18n.t.bind(i18n) as unknown as (
    key: string,
    options?: Record<string, string>,
  ) => string
  return (code: string | undefined, values?: Record<string, string>): string => {
    const key = code && i18n.exists(`errors:${code}`) ? code : 'unknown'
    return translate(`errors:${key}`, values)
  }
}

/**
 * Put field errors from a 422 problem onto the form; returns the code to show
 * as a form-level message when no field matched.
 */
export function applyServerErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fields: readonly Path<T>[],
): string | null {
  if (!(error instanceof ApiError)) return 'unknown'
  let matched = false
  for (const fieldError of error.errors) {
    if ((fields as readonly string[]).includes(fieldError.field)) {
      setError(fieldError.field as Path<T>, { type: 'server', message: fieldError.code })
      matched = true
    }
  }
  return matched ? null : error.code
}
