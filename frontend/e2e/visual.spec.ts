import { expect, test, type Page } from '@playwright/test'

import { admin, signIn } from './support.ts'

// UX-14: visual baselines for every page, in English and Bulgarian, at 1440 and 768 px.
// Run with `pnpm e2e:visual` (its own project; baselines are platform specific, see
// docs/loops/ui-polish-progress.md). Update them with `pnpm e2e:visual --update-snapshots`.
//
// The E2E database grows with every run, so lists would never look the same twice:
// GET responses are made deterministic in the browser (lists emptied, so pages show their
// empty states) and what still changes (dates, dashboard figures, charts) is masked.

const WIDTHS = [1440, 768] as const
const SIGNED_OUT = [
  ['sign-in', '/sign-in'],
  ['forgot-password', '/forgot-password'],
  ['set-password-used-link', '/set-password#token=used'],
] as const
const PAGES = [
  ['home', '/'],
  ['organizations', '/organizations'],
  ['organization-new', '/organizations/new'],
  ['contacts', '/contacts'],
  ['contact-new', '/contacts/new'],
  ['leads', '/leads'],
  ['lead-new', '/leads/new'],
  ['opportunities', '/opportunities'],
  ['opportunity-new', '/opportunities/new'],
  ['board', '/opportunities/board'],
  ['tasks', '/tasks'],
  ['win-loss', '/reports/win-loss'],
  ['search', '/search?q=visual'],
  ['profile', '/profile'],
  ['users', '/admin/users'],
  ['user-new', '/admin/users/new'],
  ['imports', '/admin/imports'],
  ['integrations', '/admin/integrations'],
  ['deliveries', '/admin/integrations/deliveries'],
  ['audit-log', '/admin/audit-log'],
  ['settings', '/admin/settings'],
  ['reference-industries', '/admin/reference/industries'],
  ['stages', '/admin/stages'],
  ['not-found', '/no-such-page'],
] as const

/** Lists that only grow between runs: shown empty. */
const EMPTY_ARRAYS = /\/(integration-clients|api-keys|webhook-subscriptions)$/

function deterministic(path: string, body: unknown): unknown {
  if (path.endsWith('/me/sessions') && Array.isArray(body)) {
    return (body as { current: boolean }[]).filter((session) => session.current)
  }
  if (EMPTY_ARRAYS.test(path) && Array.isArray(body)) return []
  if (path.endsWith('/opportunities/board') && typeof body === 'object' && body !== null) {
    const board = body as { columns: Record<string, unknown>[] }
    return {
      ...board,
      truncated: false,
      columns: board.columns.map((column) => ({
        ...column,
        cards: [],
        count: 0,
        total_amount: '0.00',
        weighted_amount: '0.00',
      })),
    }
  }
  if (typeof body === 'object' && body !== null && !Array.isArray(body)) {
    const out: Record<string, unknown> = { ...(body as Record<string, unknown>) }
    for (const key of ['items', 'matches']) if (Array.isArray(out[key])) out[key] = []
    if (typeof out.total === 'number') out.total = 0
    return out
  }
  return body
}

async function stabilise(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() !== 'GET' || path.endsWith('/me') || path.includes('/reference/')) {
      await route.fallback()
      return
    }
    const response = await route.fetch()
    const type = response.headers()['content-type'] ?? ''
    if (!response.ok() || !type.includes('application/json')) {
      await route.fulfill({ response })
      return
    }
    await route.fulfill({ response, json: deterministic(path, await response.json()) })
  })
}

/** Pages whose cards and tables show totals over the whole database. */
const FIGURES = /-(home|win-loss)$/

async function snap(page: Page, name: string) {
  await expect(page.locator('main, [role=dialog], section').first()).toBeVisible()
  await page.waitForLoadState('networkidle')
  await page.mouse.move(0, 0)
  await expect(page).toHaveScreenshot(`${name}.png`, {
    animations: 'disabled',
    caret: 'hide',
    maxDiffPixelRatio: 0.002,
    mask: [
      page.locator('time'),
      // Dates and times in text: "18 Nov 2026", "18.11.2026 г.", "17:05".
      page.getByText(/\d{1,2} [A-Z][a-z]{2} \d{4}|\d{2}\.\d{2}\.\d{4}|\b\d{1,2}:\d{2}\b/),
      page.locator('.recharts-responsive-container'),
      // Dashboard and report figures follow all the data in the database.
      ...(FIGURES.test(name) ? [page.locator('main [data-slot=card], main table')] : []),
    ],
  })
}

for (const locale of ['en', 'bg'] as const) {
  test.describe(`visual ${locale}`, () => {
    test.use({ locale: locale === 'en' ? 'en-GB' : 'bg-BG' })

    test(`UX-14 signed-out pages in ${locale}`, async ({ page }) => {
      await stabilise(page)
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 900 })
        for (const [name, path] of SIGNED_OUT) {
          await page.goto(path)
          await snap(page, `${locale}-${String(width)}-${name}`)
        }
      }
    })

    test(`UX-14 pages in ${locale}`, async ({ page }) => {
      test.setTimeout(240_000)
      const credentials = admin(locale)
      await signIn(page, credentials.email, credentials.password, {
        email: locale === 'en' ? 'Email' : 'Имейл',
        password: locale === 'en' ? 'Password' : 'Парола',
        submit: locale === 'en' ? 'Sign in' : 'Вход',
      })
      await page.waitForURL((url) => !url.pathname.startsWith('/sign-in'))

      // Records with fixed names, so their pages look the same on every run.
      const headers = { 'X-Requested-With': 'XMLHttpRequest' }
      const post = async (path: string, data: unknown) => {
        const response = await page.request.post(path, { headers, data })
        expect(response.ok(), path).toBe(true)
        return (await response.json()) as { id: string; user?: { id: string } }
      }
      const org = await post('/api/v1/organizations', {
        name: 'Визуален тест ООД',
        city: 'София',
        confirm_duplicate: true,
      })
      const contact = await post('/api/v1/contacts', {
        first_name: 'Мария',
        last_name: 'Визуална',
        organization_id: org.id,
        confirm_duplicate: true,
      })
      const lead = await post('/api/v1/leads', {
        title: 'Оптична връзка за 3 клона',
        company_name: 'Визуална фирма',
      })
      const opportunity = await post('/api/v1/opportunities', {
        name: 'Свързаност за клоновете',
        organization_id: org.id,
        amount: '48000.00',
      })
      const client = await post('/api/v1/integration-clients', {
        name: 'Visual ERP',
        system: 'erp',
      })
      const user = await post('/api/v1/users', {
        email: `visual-${locale}-${String(Date.now())}@example.test`,
        full_name: 'Visual Person',
        role: 'viewer',
      })
      const records = [
        ['organization', `/organizations/${org.id}`],
        ['organization-edit', `/organizations/${org.id}/edit`],
        ['contact', `/contacts/${contact.id}`],
        ['contact-edit', `/contacts/${contact.id}/edit`],
        ['lead', `/leads/${lead.id}`],
        ['lead-edit', `/leads/${lead.id}/edit`],
        ['lead-convert', `/leads/${lead.id}/convert`],
        ['opportunity', `/opportunities/${opportunity.id}`],
        ['opportunity-edit', `/opportunities/${opportunity.id}/edit`],
        ['user', `/admin/users/${user.user?.id ?? ''}`],
        ['integration-client', `/admin/integrations/${client.id}`],
      ] as const

      await stabilise(page)
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 900 })
        for (const [name, path] of [...PAGES, ...records]) {
          await page.goto(path)
          await snap(page, `${locale}-${String(width)}-${name}`)
        }
      }
    })
  })
}
