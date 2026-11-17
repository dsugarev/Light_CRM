import type { Schemas } from '@/api/client'

export type Activity = Schemas['ActivityOut']
export type TimelineItem = Schemas['TimelineItem']
export const ACTIVITY_TYPES = ['note', 'call', 'meeting', 'email', 'task'] as const
export type ActivityType = (typeof ACTIVITY_TYPES)[number]

/** The record a timeline or a new activity belongs to. */
export interface RecordRef {
  kind: 'lead' | 'opportunity' | 'organization' | 'contact'
  id: string
}

/** `datetime-local` input value (browser time) to an ISO timestamp, or null. */
export function toIso(local: string): string | null {
  if (!local) return null
  const date = new Date(local)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}
