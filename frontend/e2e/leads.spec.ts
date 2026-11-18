import { expect, test } from '@playwright/test'

import { admin, createUserWithPassword, expectSignedIn, mainNav, signIn } from './support.ts'

// Phase 3: leads (FR-LEAD-01..03, 05, 06) through the real stack, in both languages.

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    leads: 'Leads',
    newLead: 'New lead',
    title: 'Title',
    company: 'Company',
    create: 'Create lead',
    status: {
      new: 'New',
      contacted: 'Contacted',
      qualified: 'Qualified',
      disqualified: 'Disqualified',
    },
    markContacted: 'Mark as contacted',
    qualify: 'Qualify',
    bant: { budget: 'Budget', authority: 'Authority', need: 'Need', timeline: 'Timeline' },
    bantValue: { yes: 'Yes', partial: 'Partial', no: 'No' },
    saveBant: 'Save qualification',
    disqualify: 'Disqualify',
    disqualifyForm: 'Disqualify lead',
    reason: 'Reason',
    reasonOption: 'No budget',
    disqualifiedOn: /Disqualified on/,
    reopen: 'Reopen',
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    leads: 'Потенциални клиенти',
    newLead: 'Нов потенциален клиент',
    title: 'Заглавие',
    company: 'Фирма',
    create: 'Създай',
    status: {
      new: 'Нов',
      contacted: 'Осъществен контакт',
      qualified: 'Квалифициран',
      disqualified: 'Дисквалифициран',
    },
    markContacted: 'Отбележи контакт',
    qualify: 'Квалифицирай',
    bant: { budget: 'Бюджет', authority: 'Правомощия', need: 'Нужда', timeline: 'Срок' },
    bantValue: { yes: 'Да', partial: 'Частично', no: 'Не' },
    saveBant: 'Запази квалификацията',
    disqualify: 'Дисквалифицирай',
    disqualifyForm: 'Дисквалифициране',
    reason: 'Причина',
    reasonOption: 'Няма бюджет',
    disqualifiedOn: /Дисквалифициран на/,
    reopen: 'Отвори отново',
  },
} as const

const PASSWORD = 'Lead-Journey-Password-7'

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Leads in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-LEAD-01..03 capture, contact, qualify with BANT; disqualify and reopen', async ({
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
        `${testInfo.project.name}-${language}`,
        language,
      )

      const repContext = await browser.newContext({ locale: ui.locale, ignoreHTTPSErrors: true })
      const rep = await repContext.newPage()
      await signIn(rep, repEmail, PASSWORD, ui.signIn)
      await expectSignedIn(rep, ui.welcome)

      // Capture with a company name only (FR-LEAD-01).
      await mainNav(rep).getByRole('link', { name: ui.leads, exact: true }).click()
      await rep.getByRole('link', { name: ui.newLead }).click()
      await expect(rep.getByRole('heading', { name: ui.newLead })).toBeVisible()
      await rep.getByLabel(ui.title, { exact: true }).fill(`Fibre ${token}`)
      await rep.getByLabel(ui.company, { exact: true }).fill(`Тест Фирма ${token}`)
      await rep.getByRole('button', { name: ui.create, exact: true }).click()
      await expect(rep.getByRole('heading', { name: `Fibre ${token}` })).toBeVisible()
      await expect(rep.getByText(ui.status.new, { exact: true })).toBeVisible()

      // Lifecycle and BANT (FR-LEAD-02, FR-LEAD-03 AC1).
      await rep.getByRole('button', { name: ui.markContacted }).click()
      await expect(rep.getByText(ui.status.contacted, { exact: true })).toBeVisible()
      await expect(rep.getByRole('button', { name: ui.qualify, exact: true })).toBeDisabled()
      await rep
        .getByRole('combobox', { name: ui.bant.budget })
        .selectOption({ label: ui.bantValue.yes })
      await rep
        .getByRole('combobox', { name: ui.bant.authority })
        .selectOption({ label: ui.bantValue.partial })
      await rep
        .getByRole('combobox', { name: ui.bant.need })
        .selectOption({ label: ui.bantValue.yes })
      await rep
        .getByRole('combobox', { name: ui.bant.timeline })
        .selectOption({ label: ui.bantValue.no })
      await expect(rep.getByTestId('bant-score')).toContainText('63')
      await rep.getByRole('button', { name: ui.saveBant }).click()
      await expect(rep.getByRole('button', { name: ui.qualify, exact: true })).toBeEnabled()
      await rep.getByRole('button', { name: ui.qualify, exact: true }).click()
      await expect(rep.getByText(ui.status.qualified, { exact: true })).toBeVisible()

      // Disqualify a second lead with a reason (FR-LEAD-02 AC1).
      const headers = { 'X-Requested-With': 'XMLHttpRequest' }
      const second = await rep.request.post('/api/v1/leads', {
        headers,
        data: { title: `Lost ${token}`, company_name: `Друга ${token}` },
      })
      const lost = (await second.json()) as { id: string }
      await rep.goto(`/leads/${lost.id}`)
      await rep.getByRole('button', { name: ui.disqualify, exact: true }).click()
      const form = rep.getByRole('form', { name: ui.disqualifyForm })
      await form.getByLabel(ui.reason).selectOption({ label: ui.reasonOption })
      await form.getByRole('button', { name: ui.disqualify, exact: true }).click()
      await expect(rep.getByText(ui.disqualifiedOn)).toBeVisible()
      await expect(rep.getByRole('button', { name: ui.reopen })).toHaveCount(0)

      // A second rep cannot change the first rep's lead (FR-AUTH-05 AC1).
      const otherEmail = await createUserWithPassword(
        page,
        'sales_rep',
        PASSWORD,
        `${testInfo.project.name}-${language}-2`,
        language,
      )
      const otherContext = await browser.newContext({ locale: ui.locale, ignoreHTTPSErrors: true })
      const other = await otherContext.newPage()
      await signIn(other, otherEmail, PASSWORD, ui.signIn)
      await expectSignedIn(other, ui.welcome)
      const refused = await other.request.patch(`/api/v1/leads/${lost.id}`, {
        headers,
        data: { version: 1, title: 'Mine' },
      })
      expect(refused.status()).toBe(403)
      await otherContext.close()
      await repContext.close()

      // The Admin (Manager+) reopens it (FR-LEAD-02 AC2).
      await page.goto(`/leads/${lost.id}`)
      await page.getByRole('button', { name: ui.reopen }).click()
      await expect(page.getByText(ui.status.contacted, { exact: true })).toBeVisible()
    })
  })
}
