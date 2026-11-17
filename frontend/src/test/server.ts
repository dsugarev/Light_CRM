import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

// Default API responses for component tests; override per test with server.use().
export const handlers = [http.get('*/api/health/ready', () => HttpResponse.json({ status: 'ok' }))]

export const server = setupServer(...handlers)
