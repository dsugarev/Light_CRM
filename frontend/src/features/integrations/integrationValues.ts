import type { Schemas } from '@/api/client'

export type IntegrationClient = Schemas['IntegrationClientOut']
export type ApiKey = Schemas['ApiKeyOut']
export type Scope = IntegrationClient['scopes'][number]

/** The scopes of API spec 19.3, in the order the screens list them. */
export const SCOPES: readonly Scope[] = [
  'organizations:read',
  'organizations:write',
  'contacts:read',
  'contacts:write',
  'leads:read',
  'leads:write',
  'opportunities:read',
  'opportunities:write',
  'activities:read',
  'activities:write',
  'reference:read',
  'reports:read',
  'external-references:write',
]

/** One CIDR per line or comma; empty lines ignored. */
export function parseAllowlist(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((v) => v.trim())
    .filter(Boolean)
}

/** Requests per minute for a new client (FR-INT-08, backend default). */
export const DEFAULT_RATE_LIMIT = 300

export type Subscription = Schemas['WebhookSubscriptionOut']
export type Delivery = Schemas['WebhookDeliveryOut']
export type DeliveryStatus = Delivery['status']

/** Event types a subscription can choose (API spec 19.6); "*" means all of them. */
export const EVENT_TYPES = [
  '*',
  'organization.created',
  'organization.updated',
  'organization.archived',
  'contact.created',
  'contact.updated',
  'contact.archived',
  'contact.anonymized',
  'lead.created',
  'lead.updated',
  'lead.status_changed',
  'lead.converted',
  'opportunity.created',
  'opportunity.updated',
  'opportunity.stage_changed',
  'opportunity.closed_won',
  'opportunity.closed_lost',
  'opportunity.reopened',
  'external_reference.updated',
] as const

export const DELIVERY_STATUSES: readonly DeliveryStatus[] = [
  'pending',
  'retrying',
  'succeeded',
  'failed',
]

/** Event types in the delivery log: the subscribable ones plus the test event. */
export const LOGGED_EVENT_TYPES: readonly string[] = [
  ...EVENT_TYPES.filter((e) => e !== '*'),
  'ping',
]
