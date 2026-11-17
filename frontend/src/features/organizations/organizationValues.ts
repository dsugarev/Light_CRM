import { z } from 'zod'

import type { Schemas } from '@/api/client'

export const SIZE_BANDS = ['1-9', '10-49', '50-249', '250+'] as const
const optional = (schema: z.ZodString) => z.union([z.literal(''), schema])

export const schema = z.object({
  name: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .max(200, { error: 'validation.string_too_long' }),
  registration_number: optional(
    z
      .string()
      .trim()
      .regex(/^(\d\s*){9}((\d\s*){4})?$/, { error: 'validation.registration' }),
  ),
  vat_number: optional(
    z
      .string()
      .trim()
      .regex(/^[Bb][Gg]\s*\d{9,10}$/, { error: 'validation.vat' }),
  ),
  industry_id: z.string(),
  size_band: z.union([z.literal(''), z.enum(SIZE_BANDS)]),
  website: optional(
    z
      .string()
      .trim()
      .regex(/^https?:\/\/\S+$/i, { error: 'validation.url' }),
  ),
  address_line: z.string().max(200, { error: 'validation.string_too_long' }),
  postal_code: z.string().max(20, { error: 'validation.string_too_long' }),
  city: z.string().max(100, { error: 'validation.string_too_long' }),
  country: z
    .string()
    .trim()
    .regex(/^[A-Za-z]{2}$/, { error: 'validation.country' }),
  owner_id: z.string(),
  notes: z.string().max(5000, { error: 'validation.string_too_long' }),
})
export type OrganizationValues = z.infer<typeof schema>
export const FIELDS = Object.keys(schema.shape) as (keyof OrganizationValues)[]

type Organization = Schemas['OrganizationOut']

export function organizationDefaults(org?: Organization): OrganizationValues {
  return {
    name: org?.name ?? '',
    registration_number: org?.registration_number ?? '',
    vat_number: org?.vat_number ?? '',
    industry_id: org?.industry?.id ?? '',
    size_band: org?.size_band ?? '',
    website: org?.website ?? '',
    address_line: org?.address_line ?? '',
    postal_code: org?.postal_code ?? '',
    city: org?.city ?? '',
    country: org?.country ?? 'BG',
    owner_id: org?.owner.id ?? '',
    notes: org?.notes ?? '',
  }
}

/** Empty text becomes null so the API clears the field (PATCH) or leaves it unset. */
export function organizationPayload(values: OrganizationValues) {
  const blank = (v: string) => (v.trim() === '' ? null : v.trim())
  return {
    name: values.name.trim(),
    registration_number: blank(values.registration_number),
    vat_number: blank(values.vat_number),
    industry_id: blank(values.industry_id),
    size_band: values.size_band === '' ? null : values.size_band,
    website: blank(values.website),
    address_line: blank(values.address_line),
    postal_code: blank(values.postal_code),
    city: blank(values.city),
    country: values.country.trim().toUpperCase(),
    notes: blank(values.notes),
    ...(values.owner_id ? { owner_id: values.owner_id } : {}),
  }
}
