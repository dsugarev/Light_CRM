import { z } from 'zod'

import type { Schemas } from '@/api/client'
import type { Locale } from '@/i18n'

export type Opportunity = Schemas['OpportunityOut']
export type Stage = Schemas['StageOut']
export type StageSummary = Schemas['StageSummary']
export type BoardData = Schemas['Board']
export type BoardCard = Schemas['BoardCard']
export const STAGE_TYPES = ['open', 'won', 'lost'] as const

/** Stages carry both names; show the one for the UI language. */
export function stageName(stage: { name_en: string; name_bg: string }, locale: Locale): string {
  return locale === 'bg' ? stage.name_bg : stage.name_en
}

const money = z.union([
  z.literal(''),
  z
    .string()
    .trim()
    .regex(/^\d{1,12}([.,]\d{1,2})?$/, { error: 'validation.money' }),
])

export const schema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, { error: 'validation.required' })
      .max(200, { error: 'validation.string_too_long' }),
    organization: z.object({ id: z.string(), name: z.string() }).nullable(),
    primary_contact_id: z.string(),
    amount: money,
    expected_close_date: z.string(),
    probability: z.union([
      z.literal(''),
      z.string().regex(/^(100|[1-9]?\d)$/, { error: 'validation.probability' }),
    ]),
    next_step: z.string().max(2000, { error: 'validation.string_too_long' }),
    competitor: z.string().max(200, { error: 'validation.string_too_long' }),
    description: z.string().max(5000, { error: 'validation.string_too_long' }),
  })
  .refine((v) => v.organization !== null, {
    path: ['organization'],
    error: 'validation.required',
  })
export type OpportunityValues = z.infer<typeof schema>
export const FIELDS = [
  'name',
  'primary_contact_id',
  'amount',
  'expected_close_date',
  'probability',
  'next_step',
  'competitor',
  'description',
] as const

export function opportunityDefaults(
  opportunity?: Opportunity,
  organization?: { id: string; name: string } | null,
): OpportunityValues {
  return {
    name: opportunity?.name ?? '',
    organization: opportunity?.organization ?? organization ?? null,
    primary_contact_id: opportunity?.primary_contact?.id ?? '',
    amount: opportunity?.amount ?? '',
    expected_close_date: opportunity?.expected_close_date ?? '',
    probability:
      opportunity?.probability_overridden === true ? String(opportunity.probability) : '',
    next_step: opportunity?.next_step ?? '',
    competitor: opportunity?.competitor ?? '',
    description: opportunity?.description ?? '',
  }
}

/** Empty text becomes null; an empty probability follows the stage default. */
export function opportunityPayload(values: OpportunityValues) {
  const blank = (v: string) => (v.trim() === '' ? null : v.trim())
  return {
    name: values.name.trim(),
    primary_contact_id: blank(values.primary_contact_id),
    amount: values.amount === '' ? null : values.amount.replace(',', '.'),
    expected_close_date: blank(values.expected_close_date),
    probability: values.probability === '' ? null : Number(values.probability),
    next_step: blank(values.next_step),
    competitor: blank(values.competitor),
    description: blank(values.description),
  }
}
