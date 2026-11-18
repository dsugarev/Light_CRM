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
