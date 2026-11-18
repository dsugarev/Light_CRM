import { expect, test } from '@playwright/test'

import { admin, expectSignedIn, signIn } from './support.ts'

// FN-05: the idle warning in two tabs of one browser. The browser clock is moved forward
// (Playwright clock); the server session stays valid, as in real use before the timeout.

test('FN-05 the idle warning appears in every tab and staying signed in closes it everywhere', async ({
  browser,
}) => {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, locale: 'en-GB' })
  await context.clock.install()
  const first = await context.newPage()
  const credentials = admin('en')
  await signIn(first, credentials.email, credentials.password, {
    email: 'Email',
    password: 'Password',
    submit: 'Sign in',
  })
  await expectSignedIn(first, /^Welcome, /)
  const me = (await (await first.request.get('/api/v1/me')).json()) as {
    session: { idle_timeout_minutes: number }
  }
  const second = await context.newPage()
  await second.goto('/leads')
  await expect(second.getByRole('heading', { level: 1, name: 'Leads' })).toBeVisible()

  // Five minutes (and a little) before the timeout, counted from a minute before the last request.
  const warnAfterMinutes = me.session.idle_timeout_minutes - 1 - 5
  await context.clock.fastForward(warnAfterMinutes * 60_000 + 5_000)
  for (const page of [first, second]) {
    await expect(page.getByRole('alertdialog', { name: 'Still there?' })).toBeVisible()
  }

  await first.getByRole('button', { name: 'Stay signed in' }).click()
  for (const page of [first, second]) {
    await expect(page.getByRole('alertdialog')).toBeHidden()
  }
  await expect(second.getByRole('heading', { level: 1, name: 'Leads' })).toBeVisible()
  await context.close()
})
