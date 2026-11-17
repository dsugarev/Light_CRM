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
]

export const server = setupServer(...handlers)
