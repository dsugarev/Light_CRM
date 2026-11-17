import { z } from 'zod'

import type { Schemas } from '@/api/client'

export type Lead = Schemas['LeadOut']
export const LEAD_STATUSES = ['new', 'contacted', 'qualified', 'converted', 'disqualified'] as const
export const BANT_ITEMS = ['budget', 'authority', 'need', 'timeline'] as const
export const BANT_STATUSES = ['unknown', 'no', 'partial', 'yes'] as const

export const schema = z.object({
  title: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .max(200, { error: 'validation.string_too_long' }),
  company_name: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .max(200, { error: 'validation.string_too_long' }),
  contact_name: z.string().max(200, { error: 'validation.string_too_long' }),
  email: z.union([z.literal(''), z.email({ error: 'validation.email' })]),
  phone: z.string().max(50, { error: 'validation.string_too_long' }),
  source_id: z.string(),
  estimated_value: z.union([
    z.literal(''),
    z
      .string()
      .trim()
      .regex(/^\d{1,12}([.,]\d{1,2})?$/, { error: 'validation.money' }),
  ]),
  description: z.string().max(5000, { error: 'validation.string_too_long' }),
  organization: z.object({ id: z.string(), name: z.string() }).nullable(),
})
export type LeadValues = z.infer<typeof schema>
export const FIELDS = [
  'title',
  'company_name',
  'contact_name',
  'email',
  'phone',
  'source_id',
  'estimated_value',
  'description',
] as const

export function leadDefaults(
  lead?: Lead,
  organization?: { id: string; name: string } | null,
): LeadValues {
  return {
    title: lead?.title ?? '',
    company_name: lead?.company_name ?? organization?.name ?? '',
    contact_name: lead?.contact_name ?? '',
    email: lead?.email ?? '',
    phone: lead?.phone ?? '',
    source_id: lead?.source?.id ?? '',
    estimated_value: lead?.estimated_value ?? '',
    description: lead?.description ?? '',
    organization: lead?.organization ?? organization ?? null,
  }
}

/** Empty text becomes null; money is sent as a decimal string with a dot. */
export function leadPayload(values: LeadValues) {
  const blank = (v: string) => (v.trim() === '' ? null : v.trim())
  return {
    title: values.title.trim(),
    company_name: values.company_name.trim(),
    contact_name: blank(values.contact_name),
    email: blank(values.email),
    phone: blank(values.phone),
    source_id: blank(values.source_id),
    estimated_value:
      values.estimated_value === '' ? null : values.estimated_value.replace(',', '.'),
    description: blank(values.description),
    organization_id: values.organization?.id ?? null,
  }
}
