import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { admin, expectSignedIn, signIn } from './support.ts'

// NFR-10 (WCAG 2.1 AA): automated axe checks on every main page (test strategy 5).
// Manual keyboard walkthroughs are recorded in docs/accessibility.md.

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

async function violations(page: Page, label: string): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  return results.violations.map((v) => {
    const detail = v.nodes
      .slice(0, 1)
      .map((n) => `${n.html.slice(0, 160)} — ${n.failureSummary ?? ''}`)
      .join('')
    return `${label}: ${v.id} (${v.impact ?? 'n/a'}, ${String(v.nodes.length)} nodes): ${detail}`
  })
}

const PAGES = [
  '/',
  '/organizations',
  '/organizations/new',
  '/contacts',
  '/contacts/new',
  '/leads',
  '/leads/new',
  '/opportunities',
  '/opportunities/new',
  '/opportunities/board',
  '/tasks',
  '/reports/win-loss',
  '/search?q=test',
  '/profile',
  '/admin/users',
  '/admin/users/new',
  '/admin/imports',
  '/admin/integrations',
  '/admin/integrations/deliveries',
  '/admin/audit-log',
  '/admin/settings',
  '/admin/reference/industries',
  '/admin/stages',
]

test('NFR-10 sign-in page', async ({ page }) => {
  await page.goto('/sign-in')
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  expect(await violations(page, '/sign-in')).toEqual([])
})

test('NFR-10 main pages, a record page and the assistant drawer', async ({ page }) => {
  test.setTimeout(120_000)
  const credentials = admin('en')
  await signIn(page, credentials.email, credentials.password, {
    email: 'Email',
    password: 'Password',
    submit: 'Sign in',
  })
  await expectSignedIn(page, /^Welcome, /)
  const found: string[] = []

  for (const path of PAGES) {
    await page.goto(path)
    await expect(page.getByRole('main')).toBeVisible()
    await page.waitForLoadState('networkidle')
    found.push(...(await violations(page, path)))
  }

  // A record page with a timeline and its forms.
  const created = await page.request.post('/api/v1/organizations', {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    data: { name: `A11y ${String(Date.now())} ООД`, confirm_duplicate: true },
  })
  const org = (await created.json()) as { id: string }
  await page.goto(`/organizations/${org.id}`)
  await page.waitForLoadState('networkidle')
  found.push(...(await violations(page, '/organizations/:id')))

  // The assistant drawer, when the stack runs with it (docker-compose.e2e.yml).
  const launcher = page.getByRole('button', { name: 'Assistant', exact: true })
  if (await launcher.isVisible()) {
    await launcher.click()
    await expect(page.getByRole('complementary', { name: 'Assistant' })).toBeVisible()
    found.push(...(await violations(page, 'assistant drawer')))
  }
  expect(found, found.join('\n')).toEqual([])
})
