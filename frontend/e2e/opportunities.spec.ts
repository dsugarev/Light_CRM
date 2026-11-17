import { expect, test, type Locator, type Page } from '@playwright/test'

import { admin, createUserWithPassword, expectSignedIn, signIn } from './support.ts'

// Phase 4a: opportunities and the pipeline board (FR-OPP-01..05) through the
// real stack, in both languages. The full lead-to-won journey follows in 4b.

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    board: 'Board',
    name: 'Name',
    amount: 'Amount (EUR)',
    create: 'Create opportunity',
    newTitle: 'New opportunity',
    stages: ['Prospecting', 'Qualification', 'Solution & Proposal', 'Negotiation'],
    moveCard: (name: string) => `Move ${name} to`,
    dragCard: (name: string) => `Drag ${name}`,
    lost: 'Lost',
    lostForm: 'Close as lost',
    lostButton: 'Close as lost',
    wonForm: 'Close as won',
    reason: 'Loss reason',
    reasonOption: 'Price',
    closeWon: 'Close as won',
    wonInfo: /^Won on /,
    lostInfo: /^Lost on .*: Price$/,
    reopenInto: 'Reopen into stage',
    reopen: 'Reopen',
    totals: /^1 opportunity · €48,000\.00 · weighted €4,800\.00$/,
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    board: 'Табло',
    name: 'Име',
    amount: 'Сума (EUR)',
    create: 'Създай',
    newTitle: 'Нова възможност',
    stages: ['Проучване', 'Квалификация', 'Решение и оферта', 'Преговори'],
    moveCard: (name: string) => `Премести ${name} в`,
    dragCard: (name: string) => `Плъзни ${name}`,
    lost: 'Загубена',
    lostForm: 'Приключване като загубена',
    lostButton: 'Приключи като загубена',
    wonForm: 'Приключване като спечелена',
    reason: 'Причина за загуба',
    reasonOption: 'Цена',
    closeWon: 'Приключи като спечелена',
    wonInfo: /^Спечелена на /,
    lostInfo: /^Загубена на .*: Цена$/,
    reopenInto: 'Отвори отново в етап',
    reopen: 'Отвори отново',
    totals: /^1 възможност · 48\s?000,00\s€ · претеглено 4\s?800,00\s€$/,
  },
} as const

const PASSWORD = 'Opportunity-Journey-Password-7'
const headers = { 'X-Requested-With': 'XMLHttpRequest' }

/** Drag with the mouse in small steps so dnd-kit's pointer sensor activates. */
async function drag(page: Page, handleName: string, target: Locator) {
  const handle = page.getByRole('button', { name: handleName })
  const from = await handle.boundingBox()
  const to = await target.boundingBox()
  if (!from || !to) throw new Error('drag source or target not visible')
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(from.x + from.width / 2 + 10, from.y + from.height / 2, { steps: 5 })
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 20 })
  await page.mouse.up()
}

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Opportunities in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-OPP-01..05 create, move on the board, close lost and won, manager reopens', async ({
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
        `${testInfo.project.name}-${language}-opp`,
        language,
      )
      const repContext = await browser.newContext({ locale: ui.locale, ignoreHTTPSErrors: true })
      const rep = await repContext.newPage()
      await signIn(rep, repEmail, PASSWORD, ui.signIn)
      await expectSignedIn(rep, ui.welcome)

      const org = await rep.request.post('/api/v1/organizations', {
        headers,
        data: { name: `Тест Мрежи ${token}`, confirm_duplicate: true },
      })
      expect(org.status()).toBe(201)
      const { id: orgId } = (await org.json()) as { id: string }

      // Create from the organization (FR-OPP-01): first stage, its probability.
      const name = `Fibre ${token}`
      await rep.goto(`/opportunities/new?organization_id=${orgId}`)
      await expect(rep.getByRole('heading', { name: ui.newTitle })).toBeVisible()
      await rep.getByLabel(ui.name, { exact: true }).fill(name)
      await rep.getByLabel(ui.amount, { exact: true }).fill('48000')
      await rep.getByRole('button', { name: ui.create, exact: true }).click()
      await expect(rep.getByRole('heading', { name })).toBeVisible()
      await expect(rep.getByText(ui.stages[0], { exact: true }).first()).toBeVisible()

      // The board (mine only) shows it with column totals (FR-OPP-03).
      await rep.goto('/opportunities/board?owner_id=me')
      const column = (stage: string) => rep.getByRole('list', { name: stage, exact: true })
      await expect(column(ui.stages[0]).getByRole('link', { name })).toBeVisible()
      await expect(rep.getByText(ui.totals)).toBeVisible()

      // Drag it with the mouse to Qualification (dnd-kit pointer sensor).
      await drag(rep, ui.dragCard(name), rep.getByRole('heading', { name: ui.stages[1] }))
      await expect(column(ui.stages[1]).getByRole('link', { name })).toBeVisible()

      // Keyboard-friendly alternative: the card's own move list, to Negotiation.
      await rep
        .getByRole('combobox', { name: ui.moveCard(name) })
        .selectOption({ label: ui.stages[3] })
      await expect(column(ui.stages[3]).getByRole('link', { name })).toBeVisible()

      // Close another as lost from the board: Lost asks for a reason (FR-OPP-05).
      const second = await rep.request.post('/api/v1/opportunities', {
        headers,
        data: { name: `Lost ${token}`, organization_id: orgId, amount: '1000' },
      })
      expect(second.status()).toBe(201)
      const lostOpp = (await second.json()) as { id: string }
      await rep.reload()
      await expect(column(ui.stages[0]).getByRole('link', { name: `Lost ${token}` })).toBeVisible()
      await rep
        .getByRole('combobox', { name: ui.moveCard(`Lost ${token}`) })
        .selectOption({ label: ui.lost })
      const form = rep.getByRole('form', { name: ui.lostForm })
      await form.getByLabel(ui.reason).selectOption({ label: ui.reasonOption })
      await form.getByRole('button', { name: ui.lostButton }).click()
      await expect(rep.getByRole('link', { name: `Lost ${token}` })).toHaveCount(0)
      await expect(column(ui.stages[3]).getByRole('link', { name })).toBeVisible()

      await repContext.close()

      // The Admin (Manager+) reopens the lost one into Negotiation.
      await page.goto(`/opportunities/${lostOpp.id}`)
      await expect(page.getByText(ui.lostInfo)).toBeVisible()
      await page
        .getByRole('combobox', { name: ui.reopenInto })
        .selectOption({ label: ui.stages[3] })
      await page.getByRole('button', { name: ui.reopen, exact: true }).click()
      await expect(page.getByText(ui.stages[3], { exact: true }).first()).toBeVisible()

      // And closes it as won from the detail page.
      await page.getByRole('button', { name: ui.closeWon }).first().click()
      await page
        .getByRole('form', { name: ui.wonForm })
        .getByRole('button', { name: ui.closeWon })
        .click()
      await expect(page.getByText(ui.wonInfo)).toBeVisible()
    })
  })
}
