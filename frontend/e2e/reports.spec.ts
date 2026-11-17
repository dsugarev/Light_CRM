import { readFile } from 'node:fs/promises'

import { expect, test } from '@playwright/test'

import { admin, createUserWithPassword, expectSignedIn, signIn } from './support.ts'

// Phase 5a: dashboard figures and list exports (FR-REP-01, FR-REP-02) through the
// real stack, in both languages.

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    owner: 'Owner',
    mine: 'Mine',
    pipelineTable: 'Open pipeline by stage',
    stage: 'Negotiation',
    exportCsv: 'Export CSV',
    header: 'Opportunity',
    winLoss: 'Win/loss report',
    total: /Total 1/,
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    owner: 'Отговорник',
    mine: 'Моите',
    pipelineTable: 'Отворени възможности по етапи',
    stage: 'Преговори',
    exportCsv: 'Експорт CSV',
    header: 'Възможност',
    winLoss: 'Спечелени и загубени',
    total: /Общо 1/,
  },
} as const

const PASSWORD = 'Reports-Journey-Password-7'
const headers = { 'X-Requested-With': 'XMLHttpRequest' }

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Reports in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-REP-01..03 dashboard for my opportunities, list export, win/loss', async ({
      page,
      browser,
    }, testInfo) => {
      const token = `${String(Date.now()).slice(-6)}${testInfo.project.name.slice(0, 1)}${language}`
      const credentials = admin(language)
      await signIn(page, credentials.email, credentials.password, ui.signIn)
      await expectSignedIn(page, ui.welcome)
      const repEmail = await createUserWithPassword(
        page,
        'sales_rep',
        PASSWORD,
        `${testInfo.project.name}-${language}-reports`,
        language,
      )
      const context = await browser.newContext({
        locale: ui.locale,
        ignoreHTTPSErrors: true,
        acceptDownloads: true,
      })
      const rep = await context.newPage()
      await signIn(rep, repEmail, PASSWORD, ui.signIn)
      await expectSignedIn(rep, ui.welcome)

      // Data for this rep: one open deal in Negotiation, one won.
      const org = await rep.request.post('/api/v1/organizations', {
        headers,
        data: { name: `Отчети ${token}`, confirm_duplicate: true },
      })
      const { id: orgId } = (await org.json()) as { id: string }
      const [pipeline] = (await (await rep.request.get('/api/v1/pipelines')).json()) as {
        stages: { id: string; name_en: string }[]
      }[]
      const negotiation = pipeline.stages.find((s) => s.name_en === 'Negotiation')?.id
      await rep.request.post('/api/v1/opportunities', {
        headers,
        data: {
          name: `Open ${token}`,
          organization_id: orgId,
          amount: '10000',
          stage_id: negotiation,
        },
      })
      const won = (await (
        await rep.request.post('/api/v1/opportunities', {
          headers,
          data: { name: `Won ${token}`, organization_id: orgId, amount: '500' },
        })
      ).json()) as { id: string; version: number }
      await rep.request.post(`/api/v1/opportunities/${won.id}/close`, {
        headers,
        data: { outcome: 'won', version: won.version },
      })

      // Dashboard, my figures only (FR-REP-01).
      await rep.goto('/')
      await rep.getByRole('combobox', { name: ui.owner }).selectOption({ label: ui.mine })
      const stages = rep.getByRole('table', { name: ui.pipelineTable })
      await expect(stages.getByRole('row').filter({ hasText: ui.stage })).toContainText(/1/)
      await expect(stages).toContainText(/10\s?000|10,000/)

      // Export the opportunity list as CSV (FR-REP-02).
      await rep.goto(`/opportunities?q=${token}`)
      const downloadPromise = rep.waitForEvent('download')
      await rep.getByRole('button', { name: ui.exportCsv }).click()
      const download = await downloadPromise
      expect(download.suggestedFilename()).toMatch(/^opportunities-\d{4}-\d{2}-\d{2}\.csv$/)
      const file = await readFile(await download.path(), 'utf-8')
      expect(file.charCodeAt(0)).toBe(0xfeff)
      expect(file).toContain(ui.header)
      expect(file).toContain(`Open ${token}`)
      expect(file).toContain(`Won ${token}`)

      // Win/loss report (FR-REP-03).
      await rep.goto('/reports/win-loss?owner=me')
      const table = rep.getByRole('table', { name: ui.winLoss })
      await expect(table.getByRole('row', { name: ui.total })).toBeVisible()
      await context.close()
    })
  })
}
