import { expect, test } from '@playwright/test'

import { admin, expectSignedIn, signIn } from './support.ts'

// UX-13: with Bulgarian text at 768 px no page scrolls sideways, no list table needs
// sideways scrolling, and no filter select cuts its chosen option. The board is
// excluded: its columns scroll sideways by design.

const PAGES = [
  '/',
  '/organizations',
  '/contacts',
  '/leads',
  '/opportunities',
  '/tasks',
  '/reports/win-loss',
  '/profile',
  '/admin/users',
  '/admin/imports',
  '/admin/integrations',
  '/admin/integrations/deliveries',
  '/admin/audit-log',
  '/admin/settings',
  '/admin/reference/industries',
  '/admin/stages',
]

// Runs in the page (the e2e tsconfig has no DOM types).
const LAYOUT = `(() => {
  const problems = []
  const page = document.documentElement.scrollWidth - window.innerWidth
  if (page > 0) problems.push('page scrolls sideways by ' + page + 'px')
  for (const box of document.querySelectorAll('main [data-slot=table-container]')) {
    if (box.scrollWidth > box.clientWidth + 1) {
      const name = box.querySelector('caption')?.textContent || box.querySelector('th')?.textContent
      problems.push('table "' + name + '" scrolls by ' + (box.scrollWidth - box.clientWidth) + 'px')
    }
  }
  for (const select of document.querySelectorAll('main select')) {
    const option = select.selectedOptions[0]
    if (!option) continue
    const probe = document.createElement('span')
    probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:' + getComputedStyle(select).font
    probe.textContent = option.textContent
    document.body.appendChild(probe)
    // Text, side padding and the arrow.
    const needed = probe.offsetWidth + 30
    probe.remove()
    if (needed > select.clientWidth) problems.push('select cuts "' + option.textContent + '"')
  }
  return problems
})()`

test('UX-13 Bulgarian at 768 px: no sideways scrolling or cut filter labels', async ({ page }) => {
  test.setTimeout(120_000)
  const credentials = admin('bg')
  await signIn(page, credentials.email, credentials.password, {
    email: 'Email',
    password: 'Password',
    submit: 'Sign in',
  })
  await expectSignedIn(page, /^Добре дошли, /)
  await page.setViewportSize({ width: 768, height: 900 })
  const found: string[] = []
  for (const path of PAGES) {
    await page.goto(path)
    await expect(page.getByRole('main')).toBeVisible()
    await page.waitForLoadState('networkidle')
    for (const problem of await page.evaluate<string[]>(LAYOUT)) found.push(`${path}: ${problem}`)
  }
  expect(found, found.join('\n')).toEqual([])
})
