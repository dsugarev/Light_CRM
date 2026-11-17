import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ADMIN_ME, signedInAs, USER } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 25 })

beforeEach(() => {
  signedInAs(ADMIN_ME)
})

describe('FR-ADM-01 user administration', () => {
  it('lists users with translated roles and keeps filters in the URL', async () => {
    const requests: string[] = []
    server.use(
      http.get('*/api/v1/users', ({ request }) => {
        requests.push(new URL(request.url).search)
        return HttpResponse.json(
          page([
            USER,
            { ...USER, id: 'x', full_name: 'Locked Rep', role: 'sales_rep', is_locked: true },
          ]),
        )
      }),
    )
    const { router } = await renderApp('/admin/users')
    const table = await screen.findByRole('table')
    expect(within(table).getByRole('link', { name: 'Vera Viewer' })).toBeInTheDocument()
    expect(within(table).getByText('Viewer')).toBeInTheDocument()
    expect(within(table).getByText('Locked')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Role' }), 'sales_rep')
    await waitFor(() => {
      expect(router.state.location.search).toBe('?role=sales_rep')
    })
    await waitFor(() => {
      expect(requests.at(-1)).toContain('role=sales_rep')
    })
  })

  it('FR-AUTH-02 creates a user and shows the one-time link to hand over', async () => {
    let body: unknown
    server.use(
      http.post('*/api/v1/users', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(
          {
            user: { ...USER, full_name: 'Nova Rep', role: 'sales_rep' },
            set_password: {
              url: 'https://crm.example.test/set-password#token=abc',
              expires_at: '2026-11-20T09:00:00Z',
              emailed: false,
            },
          },
          { status: 201 },
        )
      }),
    )
    await renderApp('/admin/users/new')
    await userEvent.type(await screen.findByLabelText('Email'), 'nova.rep@example.test')
    await userEvent.type(screen.getByLabelText('Full name'), 'Nova Rep')
    await userEvent.click(screen.getByRole('button', { name: 'Create user' }))

    const panel = await screen.findByTestId('password-link')
    expect(within(panel).getByRole('textbox')).toHaveValue(
      'https://crm.example.test/set-password#token=abc',
    )
    expect(panel).toHaveTextContent('Email is not configured')
    expect(body).toEqual({
      email: 'nova.rep@example.test',
      full_name: 'Nova Rep',
      role: 'sales_rep',
      locale: 'en',
    })
  })

  it('validates the form and shows server field errors', async () => {
    server.use(
      http.post('*/api/v1/users', () =>
        problem(409, 'conflict.duplicate', {
          errors: [{ field: 'email', code: 'user.email_taken' }],
        }),
      ),
    )
    await renderApp('/admin/users/new')
    await userEvent.type(await screen.findByLabelText('Email'), 'not-an-email')
    await userEvent.click(screen.getByRole('button', { name: 'Create user' }))
    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
    expect(screen.getByText('Required.')).toBeInTheDocument()

    await userEvent.clear(screen.getByLabelText('Email'))
    await userEvent.type(screen.getByLabelText('Email'), 'taken@example.test')
    await userEvent.type(screen.getByLabelText('Full name'), 'Someone')
    await userEvent.click(screen.getByRole('button', { name: 'Create user' }))
    expect(await screen.findByText('A user with this email already exists.')).toBeInTheDocument()
  })

  it('deactivates a user after confirmation and explains the last-admin rule', async () => {
    server.use(
      http.get('*/api/v1/users/:id', () => HttpResponse.json(USER)),
      http.post('*/api/v1/users/:id/deactivate', () => problem(409, 'permission.last_admin')),
    )
    await renderApp(`/admin/users/${USER.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Deactivate' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Deactivate Vera Viewer?')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }))
    expect(
      await screen.findByText('At least one active administrator must remain.'),
    ).toBeInTheDocument()
  })

  it('creates a password reset link for a user', async () => {
    server.use(
      http.get('*/api/v1/users/:id', () => HttpResponse.json(USER)),
      http.post('*/api/v1/users/:id/password-reset', () =>
        HttpResponse.json({
          url: 'https://crm.example.test/set-password#token=r',
          expires_at: '2026-11-17T11:00:00Z',
          emailed: true,
        }),
      ),
    )
    await renderApp(`/admin/users/${USER.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Create password reset link' }))
    expect(await screen.findByTestId('password-link')).toHaveTextContent(
      'The link was also sent by email.',
    )
  })
})

describe('FR-ADM-03 audit log', () => {
  it('shows translated actions and filters by action', async () => {
    const requests: string[] = []
    server.use(
      http.get('*/api/v1/audit-log', ({ request }) => {
        requests.push(new URL(request.url).search)
        return HttpResponse.json({
          items: [
            {
              id: 'e1',
              occurred_at: '2026-11-17T09:00:00Z',
              actor: { type: 'anonymous', id: null, name: null },
              action: 'auth.login_failed',
              entity_type: 'user',
              entity_id: USER.id,
              ip: '10.0.0.5',
            },
            {
              id: 'e2',
              occurred_at: '2026-11-17T09:01:00Z',
              actor: { type: 'user', id: ADMIN_ME.id, name: 'Ada Admin' },
              action: 'future.action',
              entity_type: 'lead',
              entity_id: null,
              ip: null,
            },
          ],
          total: 2,
          page: 1,
          page_size: 50,
        })
      }),
    )
    await renderApp('/admin/audit-log')
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Failed sign-in')).toBeInTheDocument()
    expect(within(table).getByText('Anonymous')).toBeInTheDocument()
    expect(within(table).getByText('future.action')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Action'), 'auth.login_failed')
    await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    await waitFor(() => {
      expect(requests.at(-1)).toContain('action=auth.login_failed')
    })
  })

  it('shows before and after values as text', async () => {
    server.use(
      http.get('*/api/v1/audit-log/:id', () =>
        HttpResponse.json({
          id: 'e1',
          occurred_at: '2026-11-17T09:00:00Z',
          actor: { type: 'user', id: 'a', name: 'Ada Admin' },
          action: 'user.role_changed',
          entity_type: 'user',
          entity_id: USER.id,
          ip: null,
          before: { role: 'viewer' },
          after: { role: '<b>admin</b>' },
          details: null,
          request_id: 'req-1',
        }),
      ),
    )
    await renderApp('/admin/audit-log/e1')
    expect(await screen.findByRole('heading', { name: 'Role changed' })).toBeInTheDocument()
    expect(screen.getByText(/"role": "<b>admin<\/b>"/)).toBeInTheDocument()
    expect(document.querySelector('b')).toBeNull()
  })
})

describe('FR-AUTH-04 settings', () => {
  it('validates timeouts before saving', async () => {
    server.use(
      http.get('*/api/v1/settings', () =>
        HttpResponse.json({
          session_idle_timeout_minutes: 480,
          session_absolute_timeout_minutes: 10080,
          stale_opportunity_days: 14,
        }),
      ),
    )
    await renderApp('/admin/settings')
    const idle = await screen.findByLabelText('Sign out after inactivity (minutes)')
    await userEvent.clear(idle)
    await userEvent.type(idle, '5')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('The value is too small.')).toBeInTheDocument()
  })

  it('FR-OPP-06 saves the stale-opportunity threshold', async () => {
    let body: Record<string, unknown> = {}
    const current = {
      session_idle_timeout_minutes: 480,
      session_absolute_timeout_minutes: 10080,
      stale_opportunity_days: 14,
    }
    server.use(
      http.get('*/api/v1/settings', () => HttpResponse.json(current)),
      http.patch('*/api/v1/settings', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...current, ...body })
      }),
    )
    await renderApp('/admin/settings')
    const stale = await screen.findByLabelText(
      'Days without activity before an opportunity needs attention',
    )
    await userEvent.clear(stale)
    await userEvent.type(stale, '400')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('The value is too large.')).toBeInTheDocument()
    await userEvent.clear(stale)
    await userEvent.type(stale, '21')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      expect(body).toMatchObject({ stale_opportunity_days: 21 })
    })
  })
})
