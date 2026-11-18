import { expect, test, type Locator, type Page } from '@playwright/test'

import { admin } from './support.ts'

// NFR-10: keyboard-only walkthroughs (test strategy 5). No clicks: Tab, Enter, Escape
// and arrow keys only. Recorded in docs/accessibility.md.

/** Press Tab until `target` has focus; fails after `max` presses. */
async function tabTo(page: Page, target: Locator, max = 80) {
  for (let i = 0; i < max; i += 1) {
    const focused = await target.evaluate((el: unknown) => {
      const node = el as { ownerDocument: { activeElement: unknown } }
      return node === node.ownerDocument.activeElement
    })
    if (focused) return
    await page.keyboard.press('Tab')
  }
  throw new Error(`Could not reach ${String(target)} with Tab`)
}

async function signInWithKeyboard(page: Page) {
  const { email, password } = admin('en')
  await page.goto('/sign-in')
  await tabTo(page, page.getByLabel('Email', { exact: true }))
  await page.keyboard.type(email)
  await page.keyboard.press('Tab')
  await page.keyboard.type(password)
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: /^Welcome, / })).toBeVisible()
}

test('NFR-10 sign in, skip the navigation, create an organization by keyboard', async ({
  page,
}) => {
  await signInWithKeyboard(page)

  // The first Tab reaches "Skip to main content", which moves focus past the menu.
  await page.goto('/organizations/new')
  await page.keyboard.press('Tab')
  const skip = page.getByRole('link', { name: 'Skip to main content' })
  await expect(skip).toBeFocused()
  await expect(skip).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main')).toBeFocused()

  const name = `Keyboard ${String(Date.now())} ООД`
  await tabTo(page, page.getByLabel('Name', { exact: true }))
  await page.keyboard.type(name)
  await tabTo(page, page.getByRole('button', { name: 'Create organization' }))
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name })).toBeVisible()
})

test('NFR-10 move an opportunity to another stage without dragging', async ({ page }) => {
  await signInWithKeyboard(page)
  const headers = { 'X-Requested-With': 'XMLHttpRequest' }
  const org = await page.request.post('/api/v1/organizations', {
    headers,
    data: { name: `Board keys ${String(Date.now())} АД`, confirm_duplicate: true },
  })
  const name = `Keys deal ${String(Date.now())}`
  const opp = await page.request.post('/api/v1/opportunities', {
    headers,
    data: { name, organization_id: ((await org.json()) as { id: string }).id },
  })
  expect(opp.status()).toBe(201)

  await page.goto('/opportunities/board?owner_id=me')
  const move = page.getByRole('combobox', { name: `Move ${name} to` })
  await tabTo(page, move, 200)
  // Typing an option's first letters selects it on a closed list (Chromium, Firefox, any OS).
  await page.keyboard.type('Qualif')
  await expect(page.getByRole('list', { name: 'Qualification' }).getByText(name)).toBeVisible()
})

test('NFR-10 dialogs and the assistant drawer close with Escape and return focus', async ({
  page,
}) => {
  await signInWithKeyboard(page)
  const org = await page.request.post('/api/v1/organizations', {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    data: { name: `Dialog keys ${String(Date.now())} ЕАД`, confirm_duplicate: true },
  })
  await page.goto(`/organizations/${((await org.json()) as { id: string }).id}`)
  const archive = page.getByRole('button', { name: 'Archive' })
  await tabTo(page, archive)
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('alertdialog')
  await expect(dialog).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(archive).toBeFocused()

  const launcher = page.getByRole('button', { name: 'Assistant', exact: true })
  if (await launcher.isVisible()) {
    // Firefox does not wrap Tab from the end of the page to its start: begin at the top.
    await page.reload()
    await tabTo(page, launcher)
    await page.keyboard.press('Enter')
    const panel = page.getByRole('complementary', { name: 'Assistant' })
    await expect(panel.getByRole('textbox', { name: 'Your question' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(panel).toBeHidden()
    await expect(launcher).toBeFocused()
  }
})
