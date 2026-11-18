import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { admin, createUserWithPassword, expectSignedIn, signIn } from './support.ts'

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

  // A locked user, so the users list shows the red "Locked" badge (missed locally once).
  const locked = await createUserWithPassword(page, 'viewer', 'A11y-Locked-User-Pass-1', 'a11y')
  for (let attempt = 0; attempt < 5; attempt += 1) {
    // Wrong passwords for the new user; the Admin's own session is unaffected.
    await page.request.post('/api/v1/auth/login', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      data: { email: locked, password: 'wrong-password-for-a11y' },
    })
  }
  await page.goto(`/admin/users?q=${encodeURIComponent(locked)}`)
  await expect(page.getByText('Locked', { exact: true })).toBeVisible()
  found.push(...(await violations(page, '/admin/users (locked user)')))

  for (const path of PAGES) {
    await page.goto(path)
    // /admin/users/new opens a modal sheet over the list (UX-09), which hides the main landmark.
    await expect(page.getByRole('main').or(page.getByRole('dialog'))).toBeVisible()
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

test('UX-12 record, edit, detail and drawer pages', async ({ page }) => {
  test.setTimeout(180_000)
  const credentials = admin('en')
  await signIn(page, credentials.email, credentials.password, {
    email: 'Email',
    password: 'Password',
    submit: 'Sign in',
  })
  await expectSignedIn(page, /^Welcome, /)
  const headers = { 'X-Requested-With': 'XMLHttpRequest' }
  const token = String(Date.now())
  const post = async (path: string, data: unknown) => {
    const response = await page.request.post(path, { headers, data })
    expect(response.ok(), `${path}: ${String(response.status())}`).toBe(true)
    return (await response.json()) as { id: string; user?: { id: string } }
  }
  const get = async (path: string) =>
    (await (await page.request.get(path, { headers })).json()) as { items: { id: string }[] }

  const org = await post('/api/v1/organizations', {
    name: `A11y record ${token} ООД`,
    confirm_duplicate: true,
  })
  const contact = await post('/api/v1/contacts', {
    first_name: 'Мария',
    last_name: `Достъпна ${token}`,
    organization_id: org.id,
    confirm_duplicate: true,
  })
  const lead = await post('/api/v1/leads', { title: `A11y lead ${token}`, company_name: 'Акме' })
  const opportunity = await post('/api/v1/opportunities', {
    name: `A11y deal ${token}`,
    organization_id: org.id,
  })
  const client = await post('/api/v1/integration-clients', {
    name: `A11y client ${token}`,
    system: 'erp',
  })
  const created = await post('/api/v1/users', {
    email: `a11y-${token}@example.test`,
    full_name: 'A11y Person',
    role: 'viewer',
  })
  const entry = (await get('/api/v1/audit-log?page_size=1')).items.at(0)
  const batch = (await get('/api/v1/imports?page_size=1')).items.at(0)
  const delivery = (await get('/api/v1/webhook-deliveries?page_size=1')).items.at(0)

  const pages = [
    `/contacts/${contact.id}`,
    `/leads/${lead.id}`,
    `/opportunities/${opportunity.id}`,
    `/organizations/${org.id}/edit`,
    `/contacts/${contact.id}/edit`,
    `/leads/${lead.id}/edit`,
    `/leads/${lead.id}/convert`,
    `/opportunities/${opportunity.id}/edit`,
    `/admin/users/${created.user?.id ?? ''}`,
    `/admin/integrations/${client.id}`,
    ...(entry ? [`/admin/audit-log/${entry.id}`, `/admin/audit-log?entry=${entry.id}`] : []),
    // Present once the import and integration journeys have run against this stack.
    ...(batch ? [`/admin/imports/${batch.id}`] : []),
    ...(delivery ? [`/admin/integrations/deliveries/${delivery.id}`] : []),
    '/no-such-page',
  ]
  const found: string[] = []
  for (const path of pages) {
    await page.goto(path)
    await expect(page.getByRole('main').or(page.getByRole('dialog'))).toBeVisible()
    await page.waitForLoadState('networkidle')
    found.push(...(await violations(page, path)))
  }
  expect(found, found.join('\n')).toEqual([])
})

test('UX-12 signed-out pages: forgot password and set password', async ({ page, browser }) => {
  const credentials = admin('en')
  await signIn(page, credentials.email, credentials.password, {
    email: 'Email',
    password: 'Password',
    submit: 'Sign in',
  })
  await expectSignedIn(page, /^Welcome, /)
  const created = await page.request.post('/api/v1/users', {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    data: {
      email: `a11y-set-${String(Date.now())}@example.test`,
      full_name: 'A11y Set',
      role: 'viewer',
    },
  })
  const { set_password } = (await created.json()) as { set_password: { url: string } }
  const link = new URL(set_password.url)

  const anonymous = await (await browser.newContext({ ignoreHTTPSErrors: true })).newPage()
  const found: string[] = []
  for (const path of ['/forgot-password', link.pathname + link.hash, '/set-password#token=used']) {
    await anonymous.goto(path)
    await expect(anonymous.getByRole('heading', { level: 1 })).toBeVisible()
    await anonymous.waitForLoadState('networkidle')
    found.push(...(await violations(anonymous, path)))
  }
  expect(found, found.join('\n')).toEqual([])
})
