import { expect, test, type Locator, type Page } from '@playwright/test'

import { admin, createUserWithPassword } from './support.ts'

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

async function signInWithKeyboard(page: Page, credentials = admin('en')) {
  const { email, password } = credentials
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
  // A fresh rep, so their board holds only this deal however much data earlier runs left.
  await signInWithKeyboard(page)
  const password = 'Keyboard-Board-Walk-2026'
  const rep = await createUserWithPassword(page, 'sales_rep', password, 'keyboard-board')
  await page.context().clearCookies()
  await signInWithKeyboard(page, { email: rep, password })
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

// Runs in the page (the e2e tsconfig has no DOM types): contrast between the focus
// indicator of the focused element and the page background, both converted to sRGB
// through a canvas. Buttons and inputs draw focus with their border; links use the outline.
const FOCUS_CONTRAST = `(() => {
  const toRgb = (color) => {
    const canvas = document.createElement('canvas')
    canvas.width = 1
    canvas.height = 1
    const context = canvas.getContext('2d')
    context.fillStyle = color
    context.fillRect(0, 0, 1, 1)
    return Array.from(context.getImageData(0, 0, 1, 1).data.slice(0, 3))
  }
  const luminance = (rgb) => {
    const [r, g, b] = rgb.map((v) => {
      const c = v / 255
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
    })
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const style = getComputedStyle(document.activeElement)
  const indicator =
    style.outlineStyle !== 'none' && style.outlineWidth !== '0px'
      ? style.outlineColor
      : style.borderTopColor
  const a = luminance(toRgb(indicator))
  const b = luminance(toRgb(getComputedStyle(document.body).backgroundColor))
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
})()`

test('UX-12 focus indicators have 3:1 contrast with the page', async ({ page }) => {
  await signInWithKeyboard(page)
  await page.goto('/admin/users')
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  const targets = [
    nav.getByRole('link', { name: 'Leads' }),
    page.getByRole('button', { name: /^Actions for / }).first(),
    page.getByRole('searchbox', { name: 'Search by name or email' }),
  ]
  for (const target of targets) {
    await target.focus()
    // Keyboard focus, so :focus-visible styles apply.
    await page.keyboard.press('Shift+Tab')
    await page.keyboard.press('Tab')
    // Inputs fade their border in (transition-colors); measure the settled colour.
    await page.waitForTimeout(300)
    const ratio = await page.evaluate<number>(FOCUS_CONTRAST)
    expect(ratio, String(target)).toBeGreaterThanOrEqual(3)
  }
})
