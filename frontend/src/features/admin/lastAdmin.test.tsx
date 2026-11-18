import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ADMIN_ME, signedInAs, USER } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

const SELF = { ...USER, id: ADMIN_ME.id, full_name: ADMIN_ME.full_name, role: 'admin' as const }
const OTHER_ADMIN = { ...USER, id: 'a2', full_name: 'Second Admin', role: 'admin' as const }
const REASON = 'At least one active administrator must remain.'

/** The user list, answering the active-Admin count with `admins` users. */
function usersApi(admins: (typeof SELF)[]) {
  server.use(
    http.get('*/api/v1/users', ({ request }) => {
      const query = new URL(request.url).searchParams
      const items =
        query.get('role') === 'admin' && query.get('is_active') === 'true' ? admins : [USER, SELF]
      return HttpResponse.json({ items, total: items.length, page: 1, page_size: 25 })
    }),
    http.get(`*/api/v1/users/${SELF.id}`, () => HttpResponse.json(SELF)),
  )
}

async function editFromMenu(name: string) {
  await userEvent.click(await screen.findByRole('button', { name: `Actions for ${name}` }))
  await userEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }))
  return screen.findByRole('dialog', { name: 'Edit user' })
}

beforeEach(() => {
  signedInAs(ADMIN_ME)
})

describe('FN-08 last-admin protection', () => {
  it('FN-08 the last active Admin cannot be demoted, and the sheet says why', async () => {
    usersApi([SELF])
    let body: unknown
    server.use(
      http.patch('*/api/v1/users/:id', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(SELF)
      }),
    )
    await renderApp('/admin/users')
    const sheet = await editFromMenu(ADMIN_ME.full_name)
    const role = await within(sheet).findByLabelText('Role')
    expect(role).toBeDisabled()
    expect(role).toHaveAccessibleDescription(REASON)
    // Other changes still save, with the role unchanged.
    const name = within(sheet).getByLabelText('Full name')
    await userEvent.clear(name)
    await userEvent.type(name, 'Ada A. Admin')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
    expect(body).toMatchObject({ full_name: 'Ada A. Admin', role: 'admin' })
  })

  it('FN-08 with two active Admins the role can change', async () => {
    usersApi([SELF, OTHER_ADMIN])
    await renderApp('/admin/users')
    const sheet = await editFromMenu(ADMIN_ME.full_name)
    expect(await within(sheet).findByLabelText('Role')).toBeEnabled()
    expect(within(sheet).queryByText(REASON)).not.toBeInTheDocument()
  })

  it('FN-08 deactivating the last Admin is disabled on their page, with the reason', async () => {
    usersApi([SELF])
    await renderApp(`/admin/users/${SELF.id}`)
    expect(await screen.findByText(REASON)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Deactivate' })).toBeDisabled()
  })

  it('FN-08 the server refusal is still explained if the count was out of date', async () => {
    usersApi([SELF, OTHER_ADMIN])
    server.use(http.patch('*/api/v1/users/:id', () => problem(409, 'permission.last_admin')))
    await renderApp('/admin/users')
    const sheet = await editFromMenu(ADMIN_ME.full_name)
    await userEvent.selectOptions(await within(sheet).findByLabelText('Role'), 'viewer')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Save' }))
    expect(await within(sheet).findByRole('alert')).toHaveTextContent(REASON)
  })
})
