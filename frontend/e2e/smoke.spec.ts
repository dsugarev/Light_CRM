import { expect, test } from '@playwright/test'

// Phase 0 exit: the sign-in placeholder loads over HTTPS in both languages and
// the API behind the proxy is ready.

test.describe('English browser', () => {
  test.use({ locale: 'en-US' })

  test('FR-I18N-01 sign-in placeholder loads over HTTPS', async ({ page }) => {
    const response = await page.goto('/')
    await expect(page).toHaveURL(/^https:\/\/[^/]+\/sign-in/)
    expect(response?.headers()['strict-transport-security']).toContain('max-age=')
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByTestId('api-status')).toContainText('Online')
  })
})

test.describe('Bulgarian browser', () => {
  test.use({ locale: 'bg-BG' })

  test('FR-I18N-01 sign-in placeholder follows the browser language', async ({ page }) => {
    await page.goto('/sign-in')
    await expect(page.getByRole('heading', { name: 'Вход' })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('lang', 'bg')
    await expect(page.getByTestId('api-status')).toContainText('Работи')
  })

  test('FR-I18N-01 language can be switched to English', async ({ page }) => {
    await page.goto('/sign-in')
    await page.getByRole('button', { name: 'English' }).click()
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  })
})

test('NFR-04 security headers are set by the proxy', async ({ request }) => {
  const response = await request.get('/sign-in')
  const headers = response.headers()
  expect(headers['content-security-policy']).toContain("default-src 'self'")
  expect(headers['content-security-policy']).toContain("frame-ancestors 'none'")
  expect(headers['x-content-type-options']).toBe('nosniff')
  expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin')
})

test('NFR-08 API readiness is reachable through the proxy', async ({ request }) => {
  const response = await request.get('/api/health/ready')
  expect(response.status()).toBe(200)
  expect(await response.json()).toEqual({ status: 'ok' })
  expect(response.headers()['x-request-id']).toBeTruthy()
})
