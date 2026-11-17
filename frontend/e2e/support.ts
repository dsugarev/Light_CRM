import { expect, type Page } from '@playwright/test'

/**
 * Journeys need Admin accounts created with the CLI before the run, e.g.
 *   echo "$PASSWORD" | docker compose exec -T backend \
 *     python -m app.cli create-admin --email e2e-admin-en@example.test \
 *     --full-name "E2E Admin" --locale en --password-stdin
 */
export function admin(locale: 'en' | 'bg') {
  const email = process.env[`E2E_ADMIN_EMAIL_${locale.toUpperCase()}`]
  const password = process.env.E2E_ADMIN_PASSWORD
  if (!email || !password) {
    throw new Error(
      `Set E2E_ADMIN_EMAIL_${locale.toUpperCase()} and E2E_ADMIN_PASSWORD (see e2e/support.ts)`,
    )
  }
  return { email, password }
}

export function uniqueEmail(prefix: string, project: string) {
  return `${prefix}-${project}-${String(Date.now())}@example.test`.toLowerCase()
}

export async function signIn(
  page: Page,
  email: string,
  password: string,
  labels: { email: string; password: string; submit: string },
) {
  await page.goto('/sign-in')
  await page.getByLabel(labels.email, { exact: true }).fill(email)
  await page.getByLabel(labels.password, { exact: true }).fill(password)
  await page.getByRole('button', { name: labels.submit }).click()
}

export async function expectSignedIn(page: Page, heading: RegExp) {
  await expect(page.getByRole('heading', { name: heading })).toBeVisible()
}
