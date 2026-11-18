import { expect, test } from '@playwright/test'

import { admin, createUserWithPassword, expectSignedIn, mainNav, signIn } from './support.ts'

// FN-04: a session ended on the server (here an Admin signs the rep out everywhere)
// sends the rep to sign-in with a message, and back to where they were afterwards.

const LABELS = { email: 'Email', password: 'Password', submit: 'Sign in' }
const PASSWORD = 'Session-Expiry-Walk-2026'

test('FN-04 an ended session returns to the same page after signing in again', async ({
  page,
  browser,
}) => {
  const credentials = admin('en')
  const adminContext = await browser.newContext({ ignoreHTTPSErrors: true })
  const adminPage = await adminContext.newPage()
  await signIn(adminPage, credentials.email, credentials.password, LABELS)
  await expectSignedIn(adminPage, /^Welcome, /)
  const rep = await createUserWithPassword(adminPage, 'sales_rep', PASSWORD, 'session-expiry')
  const lookup = await adminPage.request.get(`/api/v1/users?q=${encodeURIComponent(rep)}`)
  const repId = ((await lookup.json()) as { items: { id: string }[] }).items[0]?.id ?? ''

  await signIn(page, rep, PASSWORD, LABELS)
  await expectSignedIn(page, /^Welcome, /)
  await page.goto('/contacts?q=nobody')
  await expect(page.getByRole('heading', { level: 1, name: 'Contacts' })).toBeVisible()

  const revoked = await adminPage.request.delete(`/api/v1/users/${repId}/sessions`, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  })
  expect(revoked.status()).toBe(204)

  // The next request fails with 401: sign-in, with the reason, remembering the page.
  await mainNav(page).getByRole('link', { name: 'Leads' }).click()
  await expect(
    page.getByText('Your session has ended. Sign in again to continue where you were.'),
  ).toBeVisible()
  await expect(page).toHaveURL(/\/sign-in\?next=%2Fleads&expired=1$/)

  await page.getByLabel('Email', { exact: true }).fill(rep)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/leads$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Leads' })).toBeVisible()
  await adminContext.close()
})
