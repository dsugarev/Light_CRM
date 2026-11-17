import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

// The only place that talks HTTP to the backend. Types come from the generated
// OpenAPI schema (`pnpm generate:api`); never hand-write API types.
// Same origin as the SPA: the session cookie is sent automatically, and the
// custom header satisfies the server's CSRF check (architecture section 7).
export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  credentials: 'same-origin',
  headers: { 'X-Requested-With': 'XMLHttpRequest' },
  // Resolve fetch per call so test doubles (MSW) installed later are used.
  fetch: (request) => globalThis.fetch(request),
})

export type Schemas = components['schemas']

export interface FieldError {
  field: string
  code: string
}

interface Problem {
  code?: string
  errors?: FieldError[]
  [key: string]: unknown
}

/** An RFC 9457 problem returned by the API; `code` drives the translated message. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly errors: FieldError[]
  readonly problem: Problem

  constructor(status: number, problem: Problem) {
    super(problem.code ?? `http.${String(status)}`)
    this.name = 'ApiError'
    this.status = status
    this.code = problem.code ?? 'unknown'
    this.errors = problem.errors ?? []
    this.problem = problem
  }
}

/** Unwrap an openapi-fetch result: return the data, or throw an ApiError. */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request
  if (!response.ok) {
    const problem = (error && typeof error === 'object' ? error : {}) as Problem
    throw new ApiError(response.status, problem)
  }
  return data as T
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}

interface PageEnvelope<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/**
 * List endpoints return a page envelope, or a sync envelope when `updated_since`
 * is sent (integrations only). The UI never uses sync mode, so narrow to a page.
 */
export function asPage<T>(
  data: PageEnvelope<T> | { items: T[]; next_cursor: string | null },
): PageEnvelope<T> {
  if ('total' in data) return data
  throw new Error('Expected a page envelope')
}
