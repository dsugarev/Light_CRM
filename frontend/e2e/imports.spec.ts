import { expect, test } from '@playwright/test'

import { admin, expectSignedIn, signIn } from './support.ts'

// Phase 5b: import with validation preview, commit and rollback (FR-IMP-01) through
// the real stack, in both languages, as the Admin.

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    nav: 'Import',
    file: 'File',
    upload: 'Upload',
    check: 'Save and check',
    invalidText: 'Repeats an earlier row of the file.',
    skipInvalid: 'Import, skipping invalid rows',
    rollback: 'Roll back import',
    confirm: 'Confirm',
    imported: 'Imported',
    rolledBack: 'Rolled back',
    archived: 'Archived',
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    nav: 'Импорт',
    file: 'Файл',
    upload: 'Качи',
    check: 'Запази и провери',
    invalidText: 'Повтаря по-ранен ред от файла.',
    skipInvalid: 'Импортирай без невалидните редове',
    rollback: 'Отмени импорта',
    confirm: 'Потвърди',
    imported: 'Импортиран',
    rolledBack: 'Отменен',
    archived: 'Архивиран',
  },
} as const

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Import in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-IMP-01 upload, preview with reasons, import valid rows, roll back', async ({
      page,
    }, testInfo) => {
      const token = `${String(Date.now()).slice(-6)}${testInfo.project.name.slice(0, 1)}${language}`
      const credentials = admin(language)
      await signIn(page, credentials.email, credentials.password, ui.signIn)
      await expectSignedIn(page, ui.welcome)

      const csv = [
        'Name;City',
        `Импорт Алфа ${token} ЕООД;Варна`,
        `Импорт Бета ${token} ООД;Русе`,
        `Импорт Алфа ${token} ЕООД;Бургас`,
      ].join('\r\n')
      await page.getByRole('link', { name: ui.nav, exact: true }).click()
      await page.getByLabel(ui.file, { exact: true }).setInputFiles({
        name: `orgs-${token}.csv`,
        mimeType: 'text/csv',
        buffer: Buffer.from(csv, 'utf-8'),
      })
      await page.getByRole('button', { name: ui.upload, exact: true }).click()
      await expect(page.getByRole('heading', { name: `orgs-${token}.csv` })).toBeVisible()

      await page.getByRole('button', { name: ui.check }).click()
      await expect(page.getByTestId('count-valid')).toHaveText('2')
      await expect(page.getByTestId('count-invalid')).toHaveText('1')
      await expect(page.getByText(ui.invalidText)).toBeVisible()

      await page.getByRole('button', { name: ui.skipInvalid }).click()
      await expect(page.getByText(ui.imported, { exact: true }).first()).toBeVisible()
      await expect(page.getByTestId('count-created')).toHaveText('2')
      const found = await page.request.get(`/api/v1/organizations?q=${token}`)
      expect(((await found.json()) as { total: number }).total).toBe(2)

      await page.getByRole('button', { name: ui.rollback }).click()
      await page.getByRole('button', { name: ui.confirm }).click()
      await expect(page.getByText(ui.rolledBack, { exact: true }).first()).toBeVisible()
      await expect(page.getByText(ui.archived, { exact: true }).first()).toBeVisible()
      const after = await page.request.get(`/api/v1/organizations?q=${token}`)
      expect(((await after.json()) as { total: number }).total).toBe(0)
    })
  })
}
