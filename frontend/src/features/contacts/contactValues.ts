import { z } from 'zod'

import type { Schemas } from '@/api/client'
import { SUPPORTED_LOCALES } from '@/i18n'

export const schema = z.object({
  first_name: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .max(100, { error: 'validation.string_too_long' }),
  last_name: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .max(100, { error: 'validation.string_too_long' }),
  job_title: z.string().max(150, { error: 'validation.string_too_long' }),
  email: z.union([z.literal(''), z.email({ error: 'validation.email' })]),
  phone: z.string().max(50, { error: 'validation.string_too_long' }),
  preferred_locale: z.union([z.literal(''), z.enum(SUPPORTED_LOCALES)]),
  organization: z.object({ id: z.string(), name: z.string() }).nullable(),
  notes: z.string().max(5000, { error: 'validation.string_too_long' }),
})
export type ContactValues = z.infer<typeof schema>
type Contact = Schemas['ContactOut']
export const FIELDS = [
  'first_name',
  'last_name',
  'job_title',
  'email',
  'phone',
  'preferred_locale',
  'notes',
] as const

export function contactDefaults(
  contact?: Contact,
  organization?: { id: string; name: string } | null,
): ContactValues {
  return {
    first_name: contact?.first_name ?? '',
    last_name: contact?.last_name ?? '',
    job_title: contact?.job_title ?? '',
    email: contact?.email ?? '',
    phone: contact?.phone ?? '',
    preferred_locale: contact?.preferred_locale ?? '',
    organization: contact?.organization ?? organization ?? null,
    notes: contact?.notes ?? '',
  }
}

export function contactPayload(values: ContactValues) {
  const blank = (v: string) => (v.trim() === '' ? null : v.trim())
  return {
    first_name: values.first_name.trim(),
    last_name: values.last_name.trim(),
    job_title: blank(values.job_title),
    email: blank(values.email),
    phone: blank(values.phone),
    preferred_locale: values.preferred_locale === '' ? null : values.preferred_locale,
    organization_id: values.organization?.id ?? null,
    notes: blank(values.notes),
  }
}
