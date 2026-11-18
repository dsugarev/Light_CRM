import { expect, test } from '@playwright/test'

import { admin, expectSignedIn, signIn } from './support.ts'

// Security pass (NFR-04, OWASP ASVS Level 1; docs/security/asvs-l1.md): what a browser
// actually receives through Caddy, which the backend tests cannot see.

const EXPECTED_HEADERS: Record<string, RegExp> = {
  'strict-transport-security': /max-age=31536000/,
  'x-content-type-options': /^nosniff$/,
  'referrer-policy': /^strict-origin-when-cross-origin$/,
  'content-security-policy': /frame-ancestors 'none'/,
  'permissions-policy': /camera=\(\)/,
}

test('ASVS 14.4 security headers on the app and the API, no server banner', async ({ request }) => {
  for (const path of ['/', '/sign-in', '/api/v1/system/info', '/api/health/live']) {
    const response = await request.get(path)
    const headers = response.headers()
    for (const [name, pattern] of Object.entries(EXPECTED_HEADERS)) {
      expect(headers[name], `${name} on ${path}`).toMatch(pattern)
    }
    expect(headers.server, `server header on ${path}`).toBeUndefined()
    expect(headers['content-security-policy']).toContain("script-src 'self'")
    expect(headers['content-security-policy']).not.toContain('unsafe-eval')
  }
  const api = await request.get('/api/v1/system/info')
  expect(api.status()).toBe(401)
  expect(api.headers()['cache-control']).toBe('no-store')
})

test('ASVS 3.4 session cookie flags and no CSP violations on the main pages', async ({
  page,
  context,
}) => {
  const violations: string[] = []
  page.on('console', (message) => {
    if (/Content[- ]Security[- ]Policy/i.test(message.text())) violations.push(message.text())
  })
  const credentials = admin('en')
  await signIn(page, credentials.email, credentials.password, {
    email: 'Email',
    password: 'Password',
    submit: 'Sign in',
  })
  await expectSignedIn(page, /^Welcome, /)

  const session = (await context.cookies()).find((cookie) => cookie.name === 'session')
  if (!session) throw new Error('No session cookie after sign-in')
  expect(session.httpOnly).toBe(true)
  expect(session.secure).toBe(true)
  expect(session.sameSite).toBe('Strict')
  expect(session.path).toBe('/api')

  for (const path of [
    '/organizations',
    '/contacts',
    '/leads',
    '/opportunities',
    '/opportunities/board',
    '/tasks',
    '/reports/win-loss',
    '/profile',
    '/admin/users',
    '/admin/audit-log',
  ]) {
    await page.goto(path)
    await expect(page.getByRole('main')).toBeVisible()
  }
  expect(violations).toEqual([])
})
