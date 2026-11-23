/// <reference lib="dom" />
import { expect, test, type Locator, type Page } from '@playwright/test'

/**
 * Screenshots for the user manuals in docs/manual (one manual per role). Not a test of
 * behaviour: it signs in as one fictional user per role and saves the screens each manual
 * shows. Run with `pnpm manual:screenshots` after an interface change, then review the
 * images. Needs the four manual users and their sample records (docs/manual/README.md,
 * "Keeping the manuals current") and MANUAL_PASSWORD.
 */

const OUT = '../docs/manual/images'
const VIEWPORT = { width: 1280, height: 800 }

const USERS = {
  admin: process.env.MANUAL_EMAIL_ADMIN ?? 'manual-admin@example.test',
  manager: process.env.MANUAL_EMAIL_MANAGER ?? 'manual-manager@example.test',
  rep: process.env.MANUAL_EMAIL_REP ?? 'manual-rep@example.test',
  viewer: process.env.MANUAL_EMAIL_VIEWER ?? 'manual-viewer@example.test',
} as const
type Role = keyof typeof USERS

test.use({ viewport: VIEWPORT, locale: 'en-GB', timezoneId: 'Europe/Sofia' })
test.describe.configure({ mode: 'parallel' })
test.setTimeout(180_000)

/**
 * The local database also holds records left by automated test runs ("A11y …", "E2E …").
 * They are hidden from list responses in the browser so the screenshots show only the
 * fictional sample data; nothing is changed on the server. Session lists keep only the
 * current session.
 */
const TEST_LEFTOVER = /^(a11y|e2e|визуален|visual|orgs-)/i
const NAME_FIELDS = ['name', 'full_name', 'email', 'filename', 'file_name', 'title']

function isLeftover(item: unknown): boolean {
  if (typeof item !== 'object' || item === null) return false
  const record = item as Record<string, unknown>
  const uploader = record.uploaded_by as { full_name?: string } | null | undefined
  return (
    NAME_FIELDS.some((field) => {
      const value = record[field]
      return typeof value === 'string' && TEST_LEFTOVER.test(value)
    }) || TEST_LEFTOVER.test(uploader?.full_name ?? '')
  )
}

async function tidy(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const response = await route.fetch()
    const type = response.headers()['content-type'] ?? ''
    if (!type.includes('application/json')) return route.fulfill({ response })
    const path = new URL(route.request().url()).pathname
    let body = (await response.json()) as unknown
    if (path.endsWith('/me/sessions') && Array.isArray(body)) {
      body = (body as { current: boolean }[]).filter((session) => session.current)
    } else if (Array.isArray(body)) {
      body = body.filter((item) => !isLeftover(item))
    } else if (
      typeof body === 'object' &&
      body !== null &&
      Array.isArray((body as { items?: unknown }).items)
    ) {
      const envelope = body as { items: unknown[]; total?: number }
      const items = envelope.items.filter((item) => !isLeftover(item))
      const removed = envelope.items.length - items.length
      body = {
        ...envelope,
        items,
        ...(typeof envelope.total === 'number' ? { total: envelope.total - removed } : {}),
      }
    }
    return route.fulfill({ response, json: body })
  })
}

async function signInAs(page: Page, role: Role) {
  const password = process.env.MANUAL_PASSWORD
  if (!password) throw new Error('Set MANUAL_PASSWORD (see docs/manual/README.md)')
  await tidy(page)
  await page.goto('/sign-in')
  await page.getByLabel('Email', { exact: true }).fill(USERS[role])
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: /^Welcome, / })).toBeVisible({ timeout: 20_000 })
}

/** Open a page and wait until it has settled (data loaded, entry animation over). */
async function open(page: Page, path: string) {
  await page.goto(path)
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)
}

async function shot(page: Page, name: string, options: { fullPage?: boolean } = {}) {
  await page.mouse.move(0, VIEWPORT.height - 1)
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: options.fullPage ?? false })
}

async function part(locator: Locator, name: string) {
  await locator.scrollIntoViewIfNeeded()
  await locator.screenshot({ path: `${OUT}/${name}.png` })
}

/** Draw attention to one control, as manuals do with callouts. */
async function highlight(locator: Locator) {
  await locator.evaluate((element: HTMLElement) => {
    element.style.outline = '3px solid #d9480f'
    element.style.outlineOffset = '3px'
    element.style.borderRadius = '6px'
  })
}

async function recordLink(page: Page, list: string, name: string): Promise<string> {
  await open(page, `${list}?q=${encodeURIComponent(name)}`)
  const href = await page.getByRole('link', { name, exact: true }).first().getAttribute('href')
  if (!href) throw new Error(`no record "${name}" in ${list}`)
  return href
}

test('common screens (signed out)', async ({ page }) => {
  await open(page, '/sign-in')
  await shot(page, 'common/sign-in')
  await open(page, '/forgot-password')
  await shot(page, 'common/forgot-password')
})

test('sales rep', async ({ page }) => {
  await signInAs(page, 'rep')
  await open(page, '/?owner=me')
  await shot(page, 'rep/home')
  await part(page.locator('header').first(), 'common/top-bar')
  await part(page.locator('#app-sidebar'), 'rep/sidebar')

  // Organizations and contacts
  await open(page, '/organizations?q=Sunrise')
  await shot(page, 'rep/organizations-list')
  await open(page, '/organizations/new')
  await page.getByLabel('Name', { exact: false }).first().fill('Sunrise Foods OOD')
  await page.getByLabel('City').fill('Plovdiv')
  await page.getByRole('button', { name: /^Create/ }).click()
  await page.waitForTimeout(800)
  await page.evaluate(() => {
    window.scrollTo(0, 0)
  })
  await shot(page, 'rep/organization-duplicate')
  const org = await recordLink(page, '/organizations', 'Sunrise Foods OOD')
  await open(page, org)
  await shot(page, 'rep/organization-page')
  const contact = await recordLink(page, '/contacts', 'Petar Nikolov')
  await open(page, contact)
  await shot(page, 'rep/contact-page')

  // Leads
  await open(page, '/leads?owner_id=me')
  await shot(page, 'rep/leads-list')
  await open(page, '/leads/new')
  await shot(page, 'rep/lead-new')
  const lead = await recordLink(page, '/leads', 'SD-WAN for 12 branches')
  await open(page, lead)
  await shot(page, 'rep/lead-page-full', { fullPage: true })

  // Opportunities
  await open(page, '/opportunities?owner_id=me')
  await shot(page, 'rep/opportunities-list')
  await open(page, '/opportunities/new')
  await shot(page, 'rep/opportunity-new')
  const opp = await recordLink(page, '/opportunities', 'Fibre for Sunrise Foods HQ')
  await open(page, opp)
  await shot(page, 'rep/opportunity-page')
  const path = page.getByRole('list', { name: 'Sales path' })
  await highlight(path)
  await part(path.locator('xpath=..'), 'rep/sales-path')
  await open(page, opp)
  await page.getByRole('button', { name: 'Log activity' }).click()
  await page.waitForTimeout(400)
  await part(page.locator('[data-slot="card"]', { hasText: 'Timeline' }), 'rep/log-activity')
  await open(page, opp)
  await page.getByRole('button', { name: 'Close as won' }).click()
  await page.waitForTimeout(400)
  await shot(page, 'rep/close-won')
  await open(page, opp)
  await page.getByRole('button', { name: 'Close as lost' }).click()
  await page.waitForTimeout(400)
  await shot(page, 'rep/close-lost')
  const won = await recordLink(page, '/opportunities', 'Mobile fleet for Sunrise Foods')
  await open(page, won)
  await shot(page, 'rep/opportunity-won')
  const qualified = await recordLink(page, '/leads', 'Managed Wi-Fi for Blue Coast Resorts')
  await open(page, qualified)
  await highlight(page.getByRole('link', { name: 'Convert' }))
  await shot(page, 'rep/lead-qualified')
  await open(page, `${qualified}/convert`)
  await shot(page, 'rep/lead-convert', { fullPage: true })
  await open(page, '/opportunities/board?owner_id=me')
  await shot(page, 'rep/board')
  await open(page, '/organizations?q=Sunrise')
  await highlight(page.getByRole('button', { name: 'Export XLSX' }).locator('xpath=..'))
  await shot(page, 'rep/export')

  // Tasks, reports, search, assistant, profile
  await open(page, '/tasks')
  await shot(page, 'rep/my-tasks')
  await open(page, '/reports/win-loss')
  await shot(page, 'rep/win-loss')
  await open(page, '/search?q=Sunrise')
  await shot(page, 'common/search')
  await open(page, '/profile')
  await shot(page, 'common/profile')
  await shot(page, 'common/profile-full', { fullPage: true })
})

// The assistant needs AI switched on; locally that is the E2E stack with the scripted
// model (docker-compose.e2e.yml), so its answer is an example of the format.
test('assistant', async ({ page }) => {
  await signInAs(page, 'rep')
  const opp = await recordLink(page, '/opportunities', 'Fibre for Sunrise Foods HQ')
  await open(page, opp)
  const launcher = page.getByRole('button', { name: 'Assistant' })
  test.skip((await launcher.count()) === 0, 'AI assistant is switched off on this stack')
  await launcher.click()
  await page.waitForTimeout(800)
  await shot(page, 'common/assistant')
  await page.getByRole('textbox').last().fill('What is the pipeline value by stage?')
  await page.keyboard.press('Enter')
  // Wait for the finished answer (its Copy button), not a fixed time.
  await page.getByRole('button', { name: 'Copy' }).last().waitFor({ timeout: 60_000 })
  await page.waitForTimeout(500)
  await shot(page, 'common/assistant-answer')
})

test('viewer', async ({ page }) => {
  await signInAs(page, 'viewer')
  await open(page, '/')
  await shot(page, 'viewer/home')
  await part(page.locator('#app-sidebar'), 'viewer/sidebar')
  await open(page, '/organizations?q=Sunrise')
  await shot(page, 'viewer/organizations-list')
  const opp = await recordLink(page, '/opportunities', 'Fibre for Sunrise Foods HQ')
  await open(page, opp)
  await shot(page, 'viewer/opportunity-page')
  const lead = await recordLink(page, '/leads', 'SD-WAN for 12 branches')
  await open(page, lead)
  await shot(page, 'viewer/lead-page')
  await open(page, '/opportunities/board')
  await shot(page, 'viewer/board')
  await open(page, '/reports/win-loss')
  await shot(page, 'viewer/win-loss')
})

test('sales manager', async ({ page }) => {
  await signInAs(page, 'manager')
  await open(page, '/')
  await shot(page, 'manager/home')
  await part(page.locator('#app-sidebar'), 'manager/sidebar')
  const opp = await recordLink(page, '/opportunities', 'Fibre for Sunrise Foods HQ')
  await open(page, opp)
  await open(page, opp)
  await highlight(page.getByRole('combobox', { name: 'New owner' }))
  await shot(page, 'manager/reassign')
  await open(page, '/opportunities?q=Sunrise')
  await shot(page, 'manager/opportunities-list')
  await open(page, '/leads?archived=1&q=SD-WAN')
  await shot(page, 'manager/leads-archived')
  await open(page, '/admin/imports')
  await shot(page, 'manager/imports')
  await open(page, '/reports/win-loss')
  await shot(page, 'manager/win-loss')
})

test('admin', async ({ page }) => {
  await signInAs(page, 'admin')
  await open(page, '/')
  await shot(page, 'admin/home')
  await part(page.locator('#app-sidebar'), 'admin/sidebar')
  await open(page, '/admin/users?q=manual')
  await shot(page, 'admin/users')
  await open(page, '/admin/users/new')
  await shot(page, 'admin/user-new')
  const user = await recordLink(page, '/admin/users', 'Elena Petrova')
  await open(page, user)
  await shot(page, 'admin/user-detail')
  await open(page, '/admin/settings')
  await shot(page, 'admin/settings', { fullPage: true })
  await open(page, '/admin/reference/industries')
  await shot(page, 'admin/reference-lists')
  await open(page, '/admin/stages')
  await shot(page, 'admin/stages')
  await open(page, '/admin/audit-log')
  await shot(page, 'admin/audit-log')
  await page
    .locator('tbody tr', { hasText: 'Closed as won' })
    .first()
    .getByRole('link', { name: /^Open entry/ })
    .click()
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(600)
  await shot(page, 'admin/audit-entry')
  await open(page, '/admin/integrations')
  await shot(page, 'admin/integrations')
  await open(page, '/admin/integrations/deliveries')
  await shot(page, 'admin/deliveries')
  await open(page, '/admin/imports')
  await shot(page, 'admin/imports')
  const contact = await recordLink(page, '/contacts', 'Petar Nikolov')
  await open(page, contact)
  await shot(page, 'admin/contact-gdpr', { fullPage: true })
})
