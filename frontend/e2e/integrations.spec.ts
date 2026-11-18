import { expect, request, test } from '@playwright/test'

import { admin, expectSignedIn, signIn } from './support.ts'

// Phase 6a: an Admin sets up an integration client and API key (FR-INT-01, 02, 03), and
// records an ID in another system on an organization (FR-INT-04), in both languages. The
// key is then used by a separate, cookie-less caller, as Conclusion, ERP or Billing would.

const UI = {
  en: {
    locale: 'en-US',
    signIn: { email: 'Email', password: 'Password', submit: 'Sign in' },
    welcome: /^Welcome, /,
    nav: 'Integrations',
    newClient: 'New integration client',
    name: 'Name',
    system: 'System',
    create: 'Create client',
    inactive: 'Inactive',
    activate: 'Activate',
    active: 'Active',
    createKey: 'Create key',
    label: 'Label',
    once: 'Copy the key now',
    newKey: 'New API key',
    keys: 'API keys',
    revoke: 'Revoke',
    revoked: 'Revoked',
    confirm: 'Confirm',
    addReference: 'Add an ID in another system',
    externalId: 'ID',
    url: 'Link (https)',
    save: 'Save',
  },
  bg: {
    locale: 'bg-BG',
    signIn: { email: 'Имейл', password: 'Парола', submit: 'Вход' },
    welcome: /^Добре дошли, /,
    nav: 'Интеграции',
    newClient: 'Нов клиент за интеграция',
    name: 'Име',
    system: 'Система',
    create: 'Създай клиент',
    inactive: 'Неактивен',
    activate: 'Активирай',
    active: 'Активен',
    createKey: 'Създай ключ',
    label: 'Етикет',
    once: 'Копирайте ключа сега',
    newKey: 'Нов API ключ',
    keys: 'API ключове',
    revoke: 'Отмени',
    revoked: 'Отменен',
    confirm: 'Потвърди',
    addReference: 'Добави идентификатор в друга система',
    externalId: 'Идентификатор',
    url: 'Връзка (https)',
    save: 'Запази',
  },
} as const

for (const language of ['en', 'bg'] as const) {
  const ui = UI[language]

  test.describe(`Integrations in ${language}`, () => {
    test.use({ locale: ui.locale })

    test('FR-INT-01..04 client, key shown once, scoped access, external ID, revocation', async ({
      page,
      baseURL,
    }, testInfo) => {
      const token = `${String(Date.now()).slice(-6)}${testInfo.project.name.slice(0, 1)}${language}`
      const credentials = admin(language)
      await signIn(page, credentials.email, credentials.password, ui.signIn)
      await expectSignedIn(page, ui.welcome)

      // FR-INT-01: create a client; it starts inactive.
      await page.getByRole('link', { name: ui.nav, exact: true }).click()
      const form = page.getByRole('form', { name: ui.newClient })
      await form.getByLabel(ui.name, { exact: true }).fill(`E2E ERP ${token}`)
      await form.getByLabel(ui.system, { exact: true }).selectOption('erp')
      await form.getByRole('checkbox', { name: 'organizations:read' }).check()
      await form.getByRole('button', { name: ui.create }).click()
      await expect(page.getByRole('heading', { name: `E2E ERP ${token}` })).toBeVisible()
      await expect(page.getByText(ui.inactive, { exact: true })).toBeVisible()
      await page.getByRole('button', { name: ui.activate, exact: true }).click()
      await expect(page.getByText(ui.active, { exact: true }).first()).toBeVisible()

      // FR-INT-02 AC1: the full key is shown once.
      const keyForm = page.getByRole('form', { name: ui.createKey })
      await keyForm.getByLabel(ui.label, { exact: true }).fill('Primary')
      await keyForm.getByRole('button', { name: ui.createKey }).click()
      await expect(page.getByText(ui.once)).toBeVisible()
      const key = await page.getByLabel(ui.newKey).inputValue()
      expect(key).toMatch(/^crm_[a-z]+_[0-9a-f]{16}_[A-Za-z0-9_-]{43}$/)
      await page.reload()
      await expect(page.getByRole('table', { name: ui.keys })).toBeVisible()
      await expect(page.getByText(ui.once)).toHaveCount(0)
      await expect(page.getByText(key)).toHaveCount(0)

      // FR-INT-04 AC4: an Admin records the organization's ERP ID on its page.
      const created = await page.request.post('/api/v1/organizations', {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        data: { name: `Интеграция ${token} ЕООД`, confirm_duplicate: true },
      })
      expect(created.status()).toBe(201)
      const org = (await created.json()) as { id: string }
      await page.goto(`/organizations/${org.id}`)
      const refForm = page.getByRole('form', { name: ui.addReference })
      await refForm.getByLabel(ui.system, { exact: true }).selectOption('erp')
      await refForm.getByLabel(ui.externalId, { exact: true }).fill(`C-${token}`)
      await refForm.getByLabel(ui.url, { exact: true }).fill(`https://erp.example.test/c/${token}`)
      await refForm.getByRole('button', { name: ui.save }).click()
      await expect(page.getByRole('link', { name: `C-${token}` })).toHaveAttribute(
        'href',
        `https://erp.example.test/c/${token}`,
      )

      // FR-INT-03: the key works for its scope only, from a caller without a session.
      const erp = await request.newContext({
        baseURL,
        ignoreHTTPSErrors: true,
        extraHTTPHeaders: { Authorization: `Bearer ${key}` },
      })
      try {
        const resolved = await erp.get(
          `/api/v1/external-references?system=erp&external_id=C-${token}`,
        )
        expect(resolved.status()).toBe(200)
        expect(((await resolved.json()) as { entity_id: string }).entity_id).toBe(org.id)
        expect((await erp.get(`/api/v1/organizations/${org.id}`)).status()).toBe(200)
        const leads = await erp.get('/api/v1/leads')
        expect(leads.status()).toBe(403)
        expect(((await leads.json()) as { code: string }).code).toBe('permission.scope_missing')

        // FR-INT-02 AC3: a revoked key is refused at once.
        await page.goBack()
        const keys = page.getByRole('table', { name: ui.keys })
        await keys.getByRole('button', { name: ui.revoke, exact: true }).click()
        await page.getByRole('button', { name: ui.confirm, exact: true }).click()
        await expect(keys.getByText(ui.revoked, { exact: true })).toBeVisible()
        expect((await erp.get(`/api/v1/organizations/${org.id}`)).status()).toBe(401)
      } finally {
        await erp.dispose()
      }
    })
  })
}
