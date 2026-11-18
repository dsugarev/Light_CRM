import { createHmac } from 'node:crypto'

import { expect, test } from '@playwright/test'

import { admin, createUserWithPassword, expectSignedIn, signIn } from './support.ts'

// Phase 8a in both languages: two-factor sign-in (FR-AUTH-07) for a Sales Rep, and an
// Admin anonymizing a contact (FR-ADM-04).

/** RFC 6238 TOTP (SHA-1, 6 digits, 30 s), so the test needs no extra package. */
function totp(base32: string, at = Date.now()): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const char of base32.replace(/=+$/, '')) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, '0')
  }
  const key = Buffer.from(bits.match(/.{8}/g)?.map((byte) => parseInt(byte, 2)) ?? [])
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)))
  const digest = createHmac('sha1', key).update(counter).digest()
  const offset = (digest[digest.length - 1] ?? 0) & 0x0f
  const value = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000
  return String(value).padStart(6, '0')
}

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    setUp: 'Set up two-factor sign-in',
    appCode: 'Code from the app',
    turnOn: 'Turn on',
    recovery: 'Recovery codes',
    saved: 'I have saved them',
    signOut: 'Sign out',
    codeStep: 'Two-factor sign-in',
    code: 'Code',
    verify: 'Verify',
    gdprExport: 'Export personal data',
    typeToConfirm: 'Type ANONYMIZE to confirm',
    anonymize: 'Anonymize contact',
    anonymizedOn: /^Anonymized on /,
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    setUp: 'Настрой двуфакторно влизане',
    appCode: 'Код от приложението',
    turnOn: 'Включи',
    recovery: 'Кодове за възстановяване',
    saved: 'Запазих ги',
    signOut: 'Изход',
    codeStep: 'Двуфакторно влизане',
    code: 'Код',
    verify: 'Потвърди',
    gdprExport: 'Експортирай лични данни',
    typeToConfirm: 'Въведете ANONYMIZE за потвърждение',
    anonymize: 'Анонимизирай контакта',
    anonymizedOn: /^Анонимизиран на /,
  },
} as const

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Privacy and sign-in in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-AUTH-07 a rep turns on two-factor sign-in and signs in with a recovery code', async ({
      page,
    }, testInfo) => {
      const credentials = admin(language)
      await signIn(page, credentials.email, credentials.password, ui.signIn)
      await expectSignedIn(page, ui.welcome)
      const password = `Mfa-Journey-${String(Date.now())}-Pass`
      const rep = await createUserWithPassword(
        page,
        'sales_rep',
        password,
        testInfo.project.name,
        language,
      )
      await page.context().clearCookies()

      await signIn(page, rep, password, ui.signIn)
      await expectSignedIn(page, ui.welcome)
      await page.goto('/profile')
      await page.getByRole('button', { name: ui.setUp }).click()
      const secret = (await page.locator('form code').innerText()).trim()
      await page.getByLabel(ui.appCode).fill(totp(secret))
      await page.getByRole('button', { name: ui.turnOn }).click()
      const codes = page.getByRole('region', { name: ui.recovery })
      const recoveryCode = (await codes.getByRole('listitem').first().innerText()).trim()
      expect(recoveryCode).toMatch(/^[0-9a-f]{5}-[0-9a-f]{5}$/)
      await codes.getByRole('button', { name: ui.saved }).click()

      await page.getByRole('button', { name: ui.signOut }).click()
      await expect(page).toHaveURL(/\/sign-in(\?|$)/) // sign-out finished (the session is gone)
      await signIn(page, rep, password, ui.signIn)
      await expect(page.getByRole('heading', { name: ui.codeStep })).toBeVisible()
      await page.getByLabel(ui.code, { exact: true }).fill(recoveryCode)
      await page.getByRole('button', { name: ui.verify }).click()
      await expectSignedIn(page, ui.welcome)
    })

    test('FR-ADM-04 an Admin anonymizes a contact', async ({ page }, testInfo) => {
      const token = `${String(Date.now()).slice(-6)}${testInfo.project.name.slice(0, 1)}${language}`
      const credentials = admin(language)
      await signIn(page, credentials.email, credentials.password, ui.signIn)
      await expectSignedIn(page, ui.welcome)
      const created = await page.request.post('/api/v1/contacts', {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        data: {
          first_name: 'Гергана',
          last_name: `Тестова${token}`,
          email: `gergana.${token}@example.test`,
          confirm_duplicate: true,
        },
      })
      expect(created.status()).toBe(201)
      const contact = (await created.json()) as { id: string }

      await page.goto(`/contacts/${contact.id}`)
      await expect(page.getByRole('button', { name: ui.gdprExport })).toBeVisible()
      const form = page.getByRole('form', { name: ui.anonymize })
      await form.getByLabel(ui.typeToConfirm).fill('ANONYMIZE')
      await form.getByRole('button', { name: ui.anonymize }).click()
      await expect(page.getByText(ui.anonymizedOn)).toBeVisible()
      await expect(page.getByRole('heading', { name: /^Anonymized #/ })).toBeVisible()
      await expect(page.getByText(`gergana.${token}@example.test`)).toHaveCount(0)
    })
  })
}
