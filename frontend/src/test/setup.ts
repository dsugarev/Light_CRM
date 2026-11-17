import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'

import { initI18n } from '@/i18n'

import { server } from './server'

await initI18n('en')

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
