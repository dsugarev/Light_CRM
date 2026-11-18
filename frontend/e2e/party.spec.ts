import { expect, test } from '@playwright/test'

import { admin, createUserWithPassword, expectSignedIn, mainNav, signIn } from './support.ts'

// Phase 2: organizations and contacts (FR-PARTY-01..04) through the real stack.

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    organizations: 'Organizations',
    newOrganization: 'New organization',
    name: 'Name',
    eik: 'EIK / UIC',
    city: 'City',
    create: 'Create organization',
    duplicates: 'Possible duplicates',
    addContact: 'Add contact',
    firstName: 'First name',
    lastName: 'Last name',
    email: 'Email',
    createContact: 'Create contact',
    search: 'Search organizations and contacts',
    archive: 'Archive',
    confirm: 'Confirm',
    archivedOn: /Archived on/,
    restore: 'Restore',
    edit: 'Edit',
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    organizations: 'Организации',
    newOrganization: 'Нова организация',
    name: 'Име',
    eik: 'ЕИК / БУЛСТАТ',
    city: 'Град',
    create: 'Създай организация',
    duplicates: 'Възможни дубликати',
    addContact: 'Добави контакт',
    firstName: 'Име',
    lastName: 'Фамилия',
    email: 'Имейл',
    createContact: 'Създай контакт',
    search: 'Търсене на организации и контакти',
    archive: 'Архивирай',
    confirm: 'Потвърди',
    archivedOn: /Архивирана на/,
    restore: 'Възстанови',
    edit: 'Редактирай',
  },
} as const

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Organizations and contacts in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-PARTY-01..04 create, detect duplicate, add contact, search across scripts, archive', async ({
      page,
    }, testInfo) => {
      // Unique per run, browser and language: the journeys run in parallel.
      const token = `${String(Date.now()).slice(-6)}${testInfo.project.name === 'firefox' ? '1' : '2'}${language === 'bg' ? '1' : '2'}`
      const cyrillic = `Тестова Компания ${token} ЕООД`
      const credentials = admin(language)
      await signIn(page, credentials.email, credentials.password, ui.signIn)
      await expectSignedIn(page, ui.welcome)

      // Create (FR-PARTY-01).
      await mainNav(page).getByRole('link', { name: ui.organizations, exact: true }).click()
      await page.getByRole('link', { name: ui.newOrganization }).click()
      await expect(page.getByRole('heading', { name: ui.newOrganization })).toBeVisible()
      await page.getByLabel(ui.name, { exact: true }).fill(cyrillic)
      await page.getByLabel(ui.city, { exact: true }).fill('София')
      await page.getByRole('button', { name: ui.create }).click()
      await expect(page.getByRole('heading', { name: cyrillic })).toBeVisible()
      const orgUrl = page.url()

      // AC1: the same company typed in Latin letters is flagged before saving.
      await mainNav(page).getByRole('link', { name: ui.organizations, exact: true }).click()
      await page.getByRole('link', { name: ui.newOrganization }).click()
      await page.getByLabel(ui.name, { exact: true }).fill(`Testova Kompania ${token} e.o.o.d.`)
      const warning = page.getByTestId('duplicate-matches')
      await expect(warning).toContainText(ui.duplicates)
      await expect(warning.getByRole('link', { name: cyrillic })).toBeVisible()

      // Add a contact from the 360 page (FR-PARTY-02, FR-PARTY-03).
      await page.goto(orgUrl)
      await page.getByRole('link', { name: ui.addContact }).click()
      await page.getByLabel(ui.firstName, { exact: true }).fill('Мария')
      await page.getByLabel(ui.lastName, { exact: true }).fill(`Тестова${token}`)
      await page.getByLabel(ui.email, { exact: true }).fill(`maria.${token}@example.test`)
      await page.getByRole('button', { name: ui.createContact }).click()
      await expect(page.getByRole('heading', { name: `Мария Тестова${token}` })).toBeVisible()
      await page.goto(orgUrl)
      await expect(page.getByRole('link', { name: `Мария Тестова${token}` })).toBeVisible()

      // Search from the header with the Latin transliteration (FR-PARTY-04, FR-I18N-04).
      await page.getByRole('searchbox', { name: ui.search }).fill(`testova kompania ${token}`)
      await page.getByRole('searchbox', { name: ui.search }).press('Enter')
      await expect(page.getByRole('link', { name: cyrillic })).toBeVisible()

      // Archive and restore.
      await page.goto(orgUrl)
      await page.getByRole('button', { name: ui.archive }).click()
      await page.getByRole('alertdialog').getByRole('button', { name: ui.confirm }).click()
      await expect(page.getByText(ui.archivedOn)).toBeVisible()
      await page.getByRole('button', { name: ui.restore }).click()
      await expect(page.getByRole('link', { name: ui.edit })).toBeVisible()
    })
  })
}

test.describe('Ownership', () => {
  test.use({ locale: 'en-US' })

  test('FR-AUTH-05 AC1 a sales rep cannot edit an organization owned by someone else', async ({
    page,
    browser,
  }, testInfo) => {
    const credentials = admin('en')
    await signIn(page, credentials.email, credentials.password, UI.en.signIn)
    await expectSignedIn(page, UI.en.welcome)
    const headers = { 'X-Requested-With': 'XMLHttpRequest' }
    const created = await page.request.post('/api/v1/organizations', {
      headers,
      data: {
        name: `Owned by admin ${String(Date.now())} ${testInfo.project.name}`,
        confirm_duplicate: true,
      },
    })
    expect(created.status()).toBe(201)
    const org = (await created.json()) as { id: string; name: string }
    const password = 'Rep-Password-For-E2E-1'
    const repEmail = await createUserWithPassword(
      page,
      'sales_rep',
      password,
      testInfo.project.name,
    )

    const context = await browser.newContext({ locale: 'en-US', ignoreHTTPSErrors: true })
    const rep = await context.newPage()
    await signIn(rep, repEmail, password, UI.en.signIn)
    await expectSignedIn(rep, UI.en.welcome)
    await rep.goto(`/organizations/${org.id}`)
    await expect(rep.getByRole('heading', { name: org.name })).toBeVisible()
    await expect(rep.getByRole('link', { name: 'Edit' })).toHaveCount(0)
    const attempt = await rep.request.patch(`/api/v1/organizations/${org.id}`, {
      headers,
      data: { city: 'Varna' },
    })
    expect(attempt.status()).toBe(403)
    await context.close()
  })
})
