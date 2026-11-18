import { expect, test } from '@playwright/test'

import { admin, expectSignedIn, mainNav, signIn, uniqueEmail } from './support.ts'

// Journey 1 (test strategy section 4): Admin creates a user; the user sets a
// password and signs in; lockout after repeated failures. Phase 1 exit check.

const NEW_PASSWORD = 'Winter-Harbour-Compass-77'

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    users: 'Users',
    newUser: 'New user',
    done: 'Done',
    form: { email: 'Email', fullName: 'Full name', role: 'Role', create: 'Create user' },
    roleRep: 'Sales Rep',
    setPassword: {
      password: 'New password',
      confirm: 'Repeat the new password',
      submit: 'Save password',
    },
    passwordSet: 'Your password is set. You can sign in now.',
    wrong: 'Wrong email or password.',
    locked: 'Too many failed attempts',
    auditLog: 'Audit log',
    userCreated: 'User created',
    accountLocked: 'Account locked',
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    users: 'Потребители',
    newUser: 'Нов потребител',
    done: 'Готово',
    form: { email: 'Имейл', fullName: 'Име и фамилия', role: 'Роля', create: 'Създай потребител' },
    roleRep: 'Търговски представител',
    setPassword: {
      password: 'Нова парола',
      confirm: 'Повторете новата парола',
      submit: 'Запази паролата',
    },
    passwordSet: 'Паролата е зададена. Вече можете да влезете.',
    wrong: 'Грешен имейл или парола.',
    locked: 'Твърде много неуспешни опити',
    auditLog: 'Одитен журнал',
    userCreated: 'Създаден потребител',
    accountLocked: 'Заключен профил',
  },
} as const

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Journey 1 in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-AUTH-02 admin creates a rep who sets a password, signs in and gets locked out', async ({
      browser,
      page,
    }, testInfo) => {
      const credentials = admin(language)
      const repEmail = uniqueEmail(`e2e-rep-${language}`, testInfo.project.name)
      const repName = language === 'bg' ? 'Мария Тестова' : 'Maria Testova'

      // 1. The Admin signs in and creates the Sales Rep.
      await signIn(page, credentials.email, credentials.password, ui.signIn)
      await expectSignedIn(page, ui.welcome)
      await mainNav(page).getByRole('link', { name: ui.users }).click()
      await page.getByRole('link', { name: ui.newUser }).click()
      // UX-09: the form opens in a side sheet over the list.
      const sheet = page.getByRole('dialog', { name: ui.newUser })
      await expect(sheet.getByRole('heading', { name: ui.newUser })).toBeVisible()
      await sheet.getByLabel(ui.form.email, { exact: true }).fill(repEmail)
      await sheet.getByLabel(ui.form.fullName, { exact: true }).fill(repName)
      await sheet.getByLabel(ui.form.role, { exact: true }).selectOption({ label: ui.roleRep })
      await sheet.getByRole('button', { name: ui.form.create }).click()
      const link = await sheet.getByTestId('password-link').getByRole('textbox').inputValue()
      expect(link).toMatch(/\/set-password#token=/)
      await sheet.getByRole('button', { name: ui.done }).click()
      await expect(sheet).toBeHidden()

      // 2. The rep, in a separate browser session, sets a password and signs in.
      const repContext = await browser.newContext({ locale: ui.locale, ignoreHTTPSErrors: true })
      const rep = await repContext.newPage()
      await rep.goto(new URL(link).pathname + new URL(link).hash)
      await rep.getByLabel(ui.setPassword.password, { exact: true }).fill(NEW_PASSWORD)
      await rep.getByLabel(ui.setPassword.confirm, { exact: true }).fill(NEW_PASSWORD)
      await rep.getByRole('button', { name: ui.setPassword.submit }).click()
      await expect(rep.getByText(ui.passwordSet)).toBeVisible()
      await signIn(rep, repEmail, NEW_PASSWORD, ui.signIn)
      await expectSignedIn(rep, new RegExp(`${ui.welcome.source}${repName}`))

      // The session cookie is HttpOnly, Secure and SameSite=Strict (architecture 7).
      const [cookie] = (await repContext.cookies()).filter((c) => c.name === 'session')
      expect(cookie).toMatchObject({
        httpOnly: true,
        secure: true,
        sameSite: 'Strict',
        path: '/api',
      })
      await repContext.close()

      // 3. Five wrong passwords lock the account (FR-AUTH-01 AC3).
      const attacker = await browser.newContext({ locale: ui.locale, ignoreHTTPSErrors: true })
      const attempt = await attacker.newPage()
      for (let i = 0; i < 5; i++) {
        await signIn(attempt, repEmail, `Wrong-Password-${String(i)}x`, ui.signIn)
        await expect(attempt.getByRole('alert')).toContainText(ui.wrong)
      }
      await signIn(attempt, repEmail, NEW_PASSWORD, ui.signIn)
      await expect(attempt.getByRole('alert')).toContainText(ui.locked)
      await attacker.close()

      // 4. Every step is in the audit log (FR-ADM-03).
      await mainNav(page).getByRole('link', { name: ui.auditLog }).click()
      await expect(page.getByRole('cell', { name: ui.userCreated }).first()).toBeVisible()
      await expect(page.getByRole('cell', { name: ui.accountLocked }).first()).toBeVisible()
    })
  })
}

test('NFR-04 mutating requests without the CSRF header are rejected', async ({ request }) => {
  const response = await request.post('/api/v1/auth/login', {
    data: { email: 'nobody@example.test', password: 'x' },
  })
  expect(response.status()).toBe(403)
  expect((await response.json()) as { code: string }).toMatchObject({ code: 'auth.csrf_failed' })
})

test('FR-AUTH-01 anonymous API calls get 401', async ({ request }) => {
  const response = await request.get('/api/v1/me')
  expect(response.status()).toBe(401)
})
