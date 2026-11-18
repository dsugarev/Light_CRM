import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { formatRelative } from '@/lib/format'
import { ADMIN_ME, signedInAs, USER } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 25 })
const HOUR = 3_600_000

beforeEach(() => {
  signedInAs(ADMIN_ME)
})

function usersApi(items: unknown[]) {
  const requests: URLSearchParams[] = []
  server.use(
    http.get('*/api/v1/users', ({ request }) => {
      requests.push(new URL(request.url).searchParams)
      return HttpResponse.json(page(items))
    }),
  )
  return requests
}

describe('UX-08 users table', () => {
  it('UX-08 sorts by a column and keeps the sort in the URL', async () => {
    const requests = usersApi([USER])
    const { router } = await renderApp('/admin/users')
    const table = await screen.findByRole('table', { name: 'Users' })
    const header = within(table).getByRole('columnheader', { name: /Last sign-in/ })
    expect(header).toHaveAttribute('aria-sort', 'none')
    await userEvent.click(within(header).getByRole('button'))
    await waitFor(() => {
      expect(router.state.location.search).toBe('?sort=last_login_at')
    })
    await waitFor(() => {
      expect(requests.at(-1)?.get('sort')).toBe('last_login_at')
    })
    await userEvent.click(within(header).getByRole('button'))
    await waitFor(() => {
      expect(router.state.location.search).toBe('?sort=-last_login_at')
    })
    expect(
      within(screen.getByRole('table')).getByRole('columnheader', { name: /Last sign-in/ }),
    ).toHaveAttribute('aria-sort', 'descending')
  })

  it('UX-08 reads search, filters and sort from a shared URL', async () => {
    const requests = usersApi([])
    await renderApp('/admin/users?q=vera&role=viewer&status=inactive&sort=-email')
    expect(await screen.findByText('Nothing to show.')).toBeInTheDocument()
    const query = requests.at(-1)
    expect(query?.get('q')).toBe('vera')
    expect(query?.get('role')).toBe('viewer')
    expect(query?.get('is_active')).toBe('false')
    expect(query?.get('sort')).toBe('-email')
    expect(screen.getByRole('searchbox', { name: 'Search by name or email' })).toHaveValue('vera')
  })

  it('UX-08 falls back to name for a sort the API does not accept', async () => {
    const requests = usersApi([USER])
    await renderApp('/admin/users?sort=password_hash')
    await screen.findByRole('table')
    expect(requests.at(-1)?.get('sort')).toBe('name')
  })

  it('UX-08 shows last sign-in relative with the exact time on hover', async () => {
    const lastLogin = new Date(Date.now() - 3 * HOUR).toISOString()
    usersApi([{ ...USER, last_login_at: lastLogin }])
    await renderApp('/admin/users')
    const time = await screen.findByText('3 hours ago')
    expect(time.closest('time')).toHaveAttribute('datetime', lastLogin)
    expect(time.closest('time')?.getAttribute('title')).toMatch(/\d{2}:\d{2}$/)
  })

  it('UX-08 shows status badges', async () => {
    usersApi([
      USER,
      { ...USER, id: 'l', full_name: 'Locked Rep', is_locked: true },
      { ...USER, id: 'i', full_name: 'Gone Rep', is_active: false },
    ])
    await renderApp('/admin/users')
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Active')).toBeInTheDocument()
    expect(within(table).getByText('Locked')).toBeInTheDocument()
    expect(within(table).getByText('Deactivated')).toBeInTheDocument()
  })

  it('UX-08 row action menu opens the user or unlocks a locked one', async () => {
    usersApi([USER, { ...USER, id: 'l1', full_name: 'Locked Rep', is_locked: true }])
    let unlocked = ''
    server.use(
      http.post('*/api/v1/users/:id/unlock', ({ params }) => {
        unlocked = String(params['id'])
        return HttpResponse.json({ ...USER, id: 'l1', is_locked: false })
      }),
    )
    const { router } = await renderApp('/admin/users')
    await userEvent.click(await screen.findByRole('button', { name: 'Actions for Locked Rep' }))
    const menu = await screen.findByRole('menu')
    await userEvent.click(within(menu).getByRole('menuitem', { name: 'Unlock' }))
    expect(await screen.findByText(/unlocked/i)).toBeInTheDocument()
    expect(unlocked).toBe('l1')

    await userEvent.click(screen.getByRole('button', { name: 'Actions for Vera Viewer' }))
    const second = await screen.findByRole('menu')
    expect(within(second).queryByRole('menuitem', { name: 'Unlock' })).not.toBeInTheDocument()
    await userEvent.click(within(second).getByRole('menuitem', { name: 'Open' }))
    expect(router.state.location.pathname).toBe(`/admin/users/${USER.id}`)
  })
})

describe('UX-08 relative time', () => {
  const now = Date.parse('2026-11-18T12:00:00Z')
  it.each([
    ['2026-11-18T11:59:30Z', 'en', '30 seconds ago'],
    ['2026-11-18T09:00:00Z', 'en', '3 hours ago'],
    ['2026-11-17T12:00:00Z', 'en', 'yesterday'],
    ['2026-11-04T12:00:00Z', 'en', '2 weeks ago'],
    ['2026-11-15T12:00:00Z', 'bg', 'преди 3 дни'],
  ] as const)('UX-08 %s in %s is "%s"', (iso, locale, expected) => {
    expect(formatRelative(iso, now, locale)).toBe(expected)
  })
})
