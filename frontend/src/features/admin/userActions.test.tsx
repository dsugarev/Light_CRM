import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ADMIN_ME, signedInAs, USER } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 25 })
const LINK = 'https://crm.example.test/set-password#token=reset-secret-token'
const SELF = { ...USER, id: ADMIN_ME.id, full_name: ADMIN_ME.full_name, role: 'admin' as const }
const GONE = { ...USER, id: 'gone', full_name: 'Gone Rep', is_active: false }

beforeEach(() => {
  signedInAs(ADMIN_ME)
  server.use(http.get('*/api/v1/users', () => HttpResponse.json(page([USER, SELF, GONE]))))
})

async function openMenu(name: string) {
  await userEvent.click(await screen.findByRole('button', { name: `Actions for ${name}` }))
  return screen.findByRole('menu')
}

async function confirm(name: string) {
  const dialog = await screen.findByRole('alertdialog', { name })
  await userEvent.click(within(dialog).getByRole('button', { name }))
}

describe('FN-03 admin user actions in the row menu', () => {
  it('FN-03 offers the actions that fit each user', async () => {
    await renderApp('/admin/users')
    const active = await openMenu('Vera Viewer')
    const names = within(active)
      .getAllByRole('menuitem')
      .map((item) => item.textContent)
    expect(names).toEqual([
      'Open',
      'Edit',
      'Create password reset link',
      'Sign out everywhere',
      'Deactivate',
    ])
    await userEvent.keyboard('{Escape}')
    const self = await openMenu(ADMIN_ME.full_name)
    expect(within(self).queryByRole('menuitem', { name: 'Deactivate' })).not.toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    const gone = await openMenu('Gone Rep')
    expect(within(gone).getByRole('menuitem', { name: 'Activate' })).toBeInTheDocument()
    expect(within(gone).queryByRole('menuitem', { name: 'Sign out everywhere' })).toBeNull()
  })

  it.each([
    ['Deactivate', 'deactivate', 'User deactivated.'],
    ['Sign out everywhere', 'sessions', 'All sessions ended.'],
  ])('FN-03 %s asks first and tells the result', async (label, endpoint, done) => {
    const calls: string[] = []
    server.use(
      http.post('*/api/v1/users/:id/deactivate', ({ params }) => {
        calls.push(`deactivate ${String(params['id'])}`)
        return HttpResponse.json({ ...USER, is_active: false })
      }),
      http.delete('*/api/v1/users/:id/sessions', ({ params }) => {
        calls.push(`sessions ${String(params['id'])}`)
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await renderApp('/admin/users')
    const menu = await openMenu('Vera Viewer')
    await userEvent.click(within(menu).getByRole('menuitem', { name: label }))
    const dialog = await screen.findByRole('alertdialog', { name: label })
    expect(dialog).toHaveTextContent('Vera Viewer')
    expect(calls).toEqual([])
    await userEvent.click(within(dialog).getByRole('button', { name: label }))
    expect(await screen.findByText(done)).toBeInTheDocument()
    expect(calls).toEqual([`${endpoint} ${USER.id}`])
  })

  it('FN-03 cancelling does nothing', async () => {
    let called = false
    server.use(
      http.post('*/api/v1/users/:id/deactivate', () => {
        called = true
        return HttpResponse.json(USER)
      }),
    )
    await renderApp('/admin/users')
    const menu = await openMenu('Vera Viewer')
    await userEvent.click(within(menu).getByRole('menuitem', { name: 'Deactivate' }))
    const dialog = await screen.findByRole('alertdialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    })
    expect(called).toBe(false)
  })

  it('FN-03 shows a reset link once and forgets it, in Bulgarian too', async () => {
    signedInAs({ ...ADMIN_ME, locale: 'bg' })
    server.use(
      http.post('*/api/v1/users/:id/password-reset', () =>
        HttpResponse.json({ url: LINK, expires_at: '2026-11-25T10:00:00Z', emailed: false }),
      ),
    )
    const { queryClient } = await renderApp('/admin/users', 'bg')
    await userEvent.click(await screen.findByRole('button', { name: 'Действия за Vera Viewer' }))
    const menu = await screen.findByRole('menu')
    await userEvent.click(
      within(menu).getByRole('menuitem', { name: 'Създай връзка за нова парола' }),
    )
    await confirm('Създай връзка за нова парола')
    const sheet = await screen.findByRole('dialog', { name: 'Връзка за нова парола' })
    expect(within(sheet).getByDisplayValue(LINK)).toBeInTheDocument()
    expect(within(sheet).getByText(/не се показва отново/)).toBeInTheDocument()
    await userEvent.click(within(sheet).getByRole('button', { name: 'Готово' }))
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(document.body.innerHTML).not.toContain('reset-secret-token')
    const cached = queryClient
      .getMutationCache()
      .getAll()
      .map((m) => m.state.data)
    expect(JSON.stringify(cached)).not.toContain('reset-secret-token')
  })
})
