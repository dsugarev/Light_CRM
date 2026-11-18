import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

import { admin, expectSignedIn, signIn } from './support.ts'

// UX-02: the app shell at 1440 and 768 px, by keyboard, with axe on the open drawer and menu.

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']
const LABELS = { email: 'Email', password: 'Password', submit: 'Sign in' }

test.beforeEach(async ({ page }) => {
  const credentials = admin('en')
  await signIn(page, credentials.email, credentials.password, LABELS)
  await expectSignedIn(page, /^Welcome, /)
})

test('UX-02 sidebar collapses at 1440 px and stays collapsed for the session', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(nav.getByRole('link', { name: 'Organizations' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Menu', exact: true })).toBeHidden()

  await page.getByRole('button', { name: 'Hide navigation' }).click()
  await expect(nav).toBeHidden()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Show navigation' })).toBeVisible()
  await expect(nav).toBeHidden()

  await page.getByRole('button', { name: 'Show navigation' }).click()
  await nav.getByRole('link', { name: 'Leads' }).click()
  await expect(nav.getByRole('link', { name: 'Leads' })).toHaveAttribute('aria-current', 'page')
})

test('UX-02 navigation drawer and user menu at 768 px by keyboard', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 900 })
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeHidden()

  const menuButton = page.getByRole('button', { name: 'Menu', exact: true })
  await menuButton.focus()
  await page.keyboard.press('Enter')
  const drawer = page.getByRole('dialog', { name: 'Light CRM' })
  await expect(drawer.getByRole('link', { name: 'Contacts' })).toBeVisible()
  const drawerScan = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(drawerScan.violations.map((v) => v.id)).toEqual([])
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(menuButton).toBeFocused()

  await menuButton.click()
  await drawer.getByRole('link', { name: 'Contacts' }).click()
  await expect(drawer).toBeHidden()
  await expect(page).toHaveURL(/\/contacts$/)

  const account = page.getByRole('button', { name: /^Account menu: / })
  await account.focus()
  await page.keyboard.press('Enter')
  const menu = page.getByRole('menu')
  await expect(menu.getByRole('menuitem', { name: 'Sign out' })).toBeVisible()
  const menuScan = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  expect(menuScan.violations.map((v) => v.id)).toEqual([])
  await page.keyboard.press('Escape')
  await expect(menu).toBeHidden()
  await expect(account).toBeFocused()
})

test('the browser tab names the page (WCAG 2.4.2)', async ({ page }) => {
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  await nav.getByRole('link', { name: 'Leads' }).click()
  await expect(page).toHaveTitle('Leads · Light CRM')
  await nav.getByRole('link', { name: 'Audit log' }).click()
  await expect(page).toHaveTitle('Audit log · Light CRM')
})
