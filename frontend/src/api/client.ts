import createClient from 'openapi-fetch'

import type { paths } from './schema'

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
