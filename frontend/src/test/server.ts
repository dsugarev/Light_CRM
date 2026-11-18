import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

export const problem = (status: number, code: string, extra: Record<string, unknown> = {}) =>
  HttpResponse.json(
    { type: `https://crm.internal/errors/${code}`, status, code, ...extra },
    { status },
  )

// Default API responses for component tests; override per test with server.use().
export const handlers = [
  http.get('*/api/health/ready', () => HttpResponse.json({ status: 'ok' })),
  http.get('*/api/v1/me', () => problem(401, 'auth.session_expired')),
  // Record pages show a timeline (FR-ACT-03); empty unless a test says otherwise.
  http.get('*/api/v1/:records/:id/timeline', () =>
    HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 }),
  ),
  // ...and IDs in other systems (FR-INT-04); none unless a test says otherwise.
  http.get('*/api/v1/:records/:id/external-references', () => HttpResponse.json([])),
  http.get('*/api/v1/reference/external-systems', () => HttpResponse.json([])),
  // The AI assistant is off unless a test switches it on (FR-AI-07).
  http.get('*/api/v1/assistant/status', () =>
    HttpResponse.json({
      enabled: false,
      daily_token_budget: 200000,
      used_today: 0,
      remaining_budget: 200000,
    }),
  ),
]

export const server = setupServer(...handlers)
