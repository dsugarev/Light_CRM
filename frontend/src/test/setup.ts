import '@testing-library/jest-dom/vitest'

import { cleanup, configure } from '@testing-library/react'

import { initI18n } from '@/i18n'

import { server } from './server'

await initI18n('en')

// findBy*/waitFor wait up to 3 s (default 1 s) so busy CI runners do not cause flaky failures.
configure({ asyncUtilTimeout: 3000 })

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' })
})
afterEach(() => {
  cleanup()
  server.resetHandlers()
  localStorage.clear()
})
afterAll(() => {
  server.close()
})
