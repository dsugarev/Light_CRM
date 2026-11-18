import { expect, test } from '@playwright/test'

import { admin, createUserWithPassword, expectSignedIn, mainNav, signIn } from './support.ts'

// Phase 4 exit (implementation plan): lead → qualify → convert → progress → close won,
// in English and Bulgarian, through the real stack.

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    newLead: 'New lead',
    title: 'Title',
    company: 'Company',
    contactName: 'Contact person',
    email: 'Email',
    estimatedValue: 'Estimated value (EUR)',
    createLead: 'Create lead',
    markContacted: 'Mark as contacted',
    contacted: 'Contacted',
    bant: ['Budget', 'Authority', 'Need', 'Timeline'],
    yes: 'Yes',
    saveBant: 'Save qualification',
    qualify: 'Qualify',
    qualified: 'Qualified',
    convert: 'Convert',
    convertSubmit: 'Convert',
    activityForm: 'Log activity',
    newOrganization: 'Create a new organization',
    newContact: 'Create a new contact',
    expectedClose: 'Expected close date',
    prospecting: 'Prospecting',
    timeline: 'Timeline',
    logActivity: 'Log activity',
    subject: 'Subject',
    type: 'Type',
    task: 'Task',
    due: 'Due',
    createTask: 'Create task',
    myTasks: 'My tasks',
    stage: 'Stage',
    move: 'Move',
    negotiation: 'Negotiation',
    stageChanged: 'Stage changed from Prospecting to Negotiation',
    closeWon: 'Close as won',
    wonForm: 'Close as won',
    wonInfo: /^Won on /,
    converted: 'Converted to an opportunity',
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    newLead: 'Нов потенциален клиент',
    title: 'Заглавие',
    company: 'Фирма',
    contactName: 'Лице за контакт',
    email: 'Имейл',
    estimatedValue: 'Очаквана стойност (EUR)',
    createLead: 'Създай',
    markContacted: 'Отбележи контакт',
    contacted: 'Осъществен контакт',
    bant: ['Бюджет', 'Правомощия', 'Нужда', 'Срок'],
    yes: 'Да',
    saveBant: 'Запази квалификацията',
    qualify: 'Квалифицирай',
    qualified: 'Квалифициран',
    convert: 'Превърни във възможност',
    convertSubmit: 'Превърни',
    activityForm: 'Нова активност',
    newOrganization: 'Създай нова организация',
    newContact: 'Създай нов контакт',
    expectedClose: 'Очаквана дата на приключване',
    prospecting: 'Проучване',
    timeline: 'Хронология',
    logActivity: 'Нова активност',
    subject: 'Тема',
    type: 'Вид',
    task: 'Задача',
    due: 'Срок',
    createTask: 'Създай задача',
    myTasks: 'Моите задачи',
    stage: 'Етап',
    move: 'Премести',
    negotiation: 'Преговори',
    stageChanged: 'Етапът е променен от Проучване на Преговори',
    closeWon: 'Приключи като спечелена',
    wonForm: 'Приключване като спечелена',
    wonInfo: /^Спечелена на /,
    converted: 'Превърнат във възможност',
  },
} as const

const PASSWORD = 'Full-Journey-Password-7'

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Lead to won in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-LEAD-01..04, FR-OPP-01..05, FR-ACT-01..03 lead → qualify → convert → progress → won', async ({
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
        `${testInfo.project.name}-${language}-journey`,
        language,
      )
      const context = await browser.newContext({ locale: ui.locale, ignoreHTTPSErrors: true })
      const rep = await context.newPage()
      await signIn(rep, repEmail, PASSWORD, ui.signIn)
      await expectSignedIn(rep, ui.welcome)

      // 1. Capture the lead (FR-LEAD-01).
      const title = `Branch fibre ${token}`
      const company = `Журни Мрежи ${token}`
      await rep.goto('/leads/new')
      await expect(rep.getByRole('heading', { name: ui.newLead })).toBeVisible()
      await rep.getByLabel(ui.title, { exact: true }).fill(title)
      await rep.getByLabel(ui.company, { exact: true }).fill(company)
      await rep.getByLabel(ui.contactName, { exact: true }).fill('Мария Иванова')
      await rep.getByLabel(ui.email, { exact: true }).fill(`maria.${token}@example.test`)
      await rep.getByLabel(ui.estimatedValue, { exact: true }).fill('60000')
      await rep.getByRole('button', { name: ui.createLead, exact: true }).click()
      await expect(rep.getByRole('heading', { name: title })).toBeVisible()

      // 2. Contact and qualify with BANT (FR-LEAD-02, 03).
      await rep.getByRole('button', { name: ui.markContacted }).click()
      await expect(rep.getByText(ui.contacted, { exact: true })).toBeVisible()
      for (const item of ui.bant) {
        await rep.getByRole('combobox', { name: item }).selectOption({ label: ui.yes })
      }
      await rep.getByRole('button', { name: ui.saveBant }).click()
      await expect(rep.getByTestId('bant-score')).toContainText('100')
      await rep.getByRole('button', { name: ui.qualify, exact: true }).click()
      await expect(rep.getByText(ui.qualified, { exact: true })).toBeVisible()

      // 3. Convert (FR-LEAD-04): new organization and contact, opportunity in Prospecting.
      await rep.getByRole('link', { name: ui.convert }).click()
      await rep.getByRole('radio', { name: ui.newOrganization }).check()
      await rep.getByRole('radio', { name: ui.newContact }).check()
      await rep.getByLabel(ui.expectedClose).fill('2027-03-31')
      await rep.getByRole('button', { name: ui.convertSubmit, exact: true }).click()
      await expect(rep.getByRole('heading', { name: title })).toBeVisible()
      await expect(rep).toHaveURL(/\/opportunities\//)
      await expect(rep.getByText(ui.prospecting, { exact: true }).first()).toBeVisible()
      const timeline = rep.getByRole('list', { name: ui.timeline })
      await expect(timeline.getByText(ui.converted)).toBeVisible() // source lead on the timeline

      // 4. Log a follow-up task and see it in My tasks (FR-ACT-01, 02).
      await rep.getByRole('button', { name: ui.logActivity }).click()
      const form = rep.getByRole('form', { name: ui.activityForm })
      await form.getByLabel(ui.type).selectOption({ label: ui.task })
      await form.getByLabel(ui.subject).fill(`Send the offer ${token}`)
      await form.getByLabel(ui.due).fill('2026-12-01T10:00')
      await form.getByRole('button', { name: ui.createTask }).click()
      await expect(timeline.getByText(`Send the offer ${token}`)).toBeVisible()
      await mainNav(rep).getByRole('link', { name: ui.myTasks }).click()
      await expect(
        rep.getByRole('table', { name: ui.myTasks }).getByText(`Send the offer ${token}`),
      ).toBeVisible()
      await rep.goBack()

      // 5. Progress to Negotiation; the stage change appears on the timeline (FR-OPP-02, FR-ACT-03).
      await rep
        .getByRole('combobox', { name: ui.stage, exact: true })
        .selectOption({ label: ui.negotiation })
      await rep.getByRole('button', { name: ui.move, exact: true }).click()
      await expect(timeline.getByText(ui.stageChanged)).toBeVisible()

      // 6. Close as won (FR-OPP-05).
      await rep.getByRole('button', { name: ui.closeWon }).first().click()
      await rep
        .getByRole('form', { name: ui.wonForm })
        .getByRole('button', { name: ui.closeWon })
        .click()
      await expect(rep.getByText(ui.wonInfo)).toBeVisible()
      await context.close()
    })
  })
}
