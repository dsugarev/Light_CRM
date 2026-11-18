import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ADMIN_ME, signedInAs, USER } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 25 })
const LINK = 'https://crm.example.test/set-password#token=one-time-secret-token'

beforeEach(() => {
  signedInAs(ADMIN_ME)
  server.use(http.get('*/api/v1/users', () => HttpResponse.json(page([USER]))))
})

describe('UX-09 create and edit user', () => {
  it('UX-09 creates a user in a sheet and shows the link once', async () => {
    let body: unknown
    server.use(
      http.post('*/api/v1/users', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(
          {
            user: { ...USER, id: 'new1', full_name: 'Nina New' },
            set_password: { url: LINK, expires_at: '2026-11-25T10:00:00Z', emailed: false },
          },
          { status: 201 },
        )
      }),
    )
    const { router, queryClient } = await renderApp('/admin/users')
    await userEvent.click(await screen.findByRole('link', { name: 'New user' }))
    const sheet = await screen.findByRole('dialog', { name: 'New user' })
    expect(router.state.location.pathname).toBe('/admin/users/new')
    // The list stays underneath.
    expect(
      screen.getByRole('heading', { level: 1, name: 'Users', hidden: true }),
    ).toBeInTheDocument()

    await userEvent.type(within(sheet).getByLabelText('Email'), 'nina@example.test')
    await userEvent.type(within(sheet).getByLabelText('Full name'), 'Nina New')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Create user' }))

    expect(await within(sheet).findByDisplayValue(LINK)).toBeInTheDocument()
    expect(within(sheet).getByRole('button', { name: 'Copy' })).toBeInTheDocument()
    expect(within(sheet).getByText(/expires on 25 Nov 2026/)).toBeInTheDocument()
    expect(within(sheet).getByText(/not shown again/)).toBeInTheDocument()
    expect(body).toMatchObject({ email: 'nina@example.test', full_name: 'Nina New' })

    await userEvent.click(within(sheet).getByRole('button', { name: 'Done' }))
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(router.state.location.pathname).toBe('/admin/users')
    // AC: the link is not kept anywhere in frontend state after the sheet closes.
    expect(document.body.innerHTML).not.toContain('one-time-secret-token')
    const cached = queryClient
      .getMutationCache()
      .getAll()
      .map((m) => m.state.data)
    expect(JSON.stringify(cached)).not.toContain('one-time-secret-token')
    const queries = queryClient
      .getQueryCache()
      .getAll()
      .map((q) => q.state.data)
    expect(JSON.stringify(queries)).not.toContain('one-time-secret-token')

    // Opening the sheet again starts with an empty form, not the old link.
    await userEvent.click(screen.getByRole('link', { name: 'New user' }))
    const again = await screen.findByRole('dialog', { name: 'New user' })
    expect(within(again).getByLabelText('Email')).toHaveValue('')
  })

  it('UX-09 closing with Escape also forgets the link', async () => {
    server.use(
      http.post('*/api/v1/users', () =>
        HttpResponse.json(
          {
            user: { ...USER, id: 'new2' },
            set_password: { url: LINK, expires_at: '2026-11-25T10:00:00Z', emailed: true },
          },
          { status: 201 },
        ),
      ),
    )
    const { queryClient } = await renderApp('/admin/users/new')
    const sheet = await screen.findByRole('dialog', { name: 'New user' })
    await userEvent.type(within(sheet).getByLabelText('Email'), 'x@example.test')
    await userEvent.type(within(sheet).getByLabelText('Full name'), 'X')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Create user' }))
    expect(await within(sheet).findByText('The link was also sent by email.')).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    const cached = queryClient
      .getMutationCache()
      .getAll()
      .map((m) => m.state.data)
    expect(JSON.stringify(cached)).not.toContain('one-time-secret-token')
  })

  it('UX-09 edits a user from the row menu', async () => {
    let patched: unknown
    server.use(
      http.patch('*/api/v1/users/:id', async ({ request }) => {
        patched = await request.json()
        return HttpResponse.json({ ...USER, full_name: 'Vera Renamed' })
      }),
    )
    await renderApp('/admin/users')
    await userEvent.click(await screen.findByRole('button', { name: 'Actions for Vera Viewer' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }))
    const sheet = await screen.findByRole('dialog', { name: 'Edit user' })
    const name = within(sheet).getByLabelText('Full name')
    expect(name).toHaveValue('Vera Viewer')
    await userEvent.clear(name)
    await userEvent.type(name, 'Vera Renamed')
    await userEvent.click(within(sheet).getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(patched).toMatchObject({ full_name: 'Vera Renamed' })
  })

  it('UX-09 edits from the user page, in Bulgarian too', async () => {
    signedInAs({ ...ADMIN_ME, locale: 'bg' })
    server.use(http.get(`*/api/v1/users/${USER.id}`, () => HttpResponse.json(USER)))
    await renderApp(`/admin/users/${USER.id}`, 'bg')
    await userEvent.click(await screen.findByRole('button', { name: 'Редактирай' }))
    const sheet = await screen.findByRole('dialog', { name: 'Редакция на потребител' })
    expect(within(sheet).getByLabelText('Имейл')).toHaveValue(USER.email)
  })
})
