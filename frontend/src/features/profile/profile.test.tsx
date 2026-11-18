import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

const sessions = [
  {
    id: 's1',
    created_at: '2026-11-17T07:00:00Z',
    last_seen_at: '2026-11-17T08:00:00Z',
    expires_at: '2026-11-24T07:00:00Z',
    ip: '10.0.0.1',
    user_agent: 'Firefox',
    current: true,
  },
  {
    id: 's2',
    created_at: '2026-11-16T07:00:00Z',
    last_seen_at: '2026-11-16T08:00:00Z',
    expires_at: '2026-11-23T07:00:00Z',
    ip: '10.0.0.2',
    user_agent: 'Phone',
    current: false,
  },
]

beforeEach(() => {
  signedInAs(REP_ME)
  server.use(http.get('*/api/v1/me/sessions', () => HttpResponse.json(sessions)))
})

describe('profile', () => {
  it('FR-AUTH-04 lists sessions and signs out another one', async () => {
    let revoked = ''
    server.use(
      http.delete('*/api/v1/me/sessions/:id', ({ params }) => {
        revoked = String(params['id'])
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await renderApp('/profile')
    const table = await screen.findByRole('table')
    expect(within(table).getByText('This session')).toBeInTheDocument()
    await userEvent.click(within(table).getByRole('button', { name: 'Sign out' }))
    // UX-05: a destructive action waits for confirmation.
    const dialog = await screen.findByRole('alertdialog', { name: 'Sign out this session?' })
    expect(revoked).toBe('')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Confirm' }))
    expect(await screen.findByText('That session is signed out.')).toBeInTheDocument()
    expect(revoked).toBe('s2')
  })

  it('FR-AUTH-03 checks the new password before calling the API', async () => {
    await renderApp('/profile')
    await userEvent.type(await screen.findByLabelText('Current password'), 'old')
    await userEvent.type(screen.getByLabelText('New password'), 'short')
    await userEvent.type(screen.getByLabelText('Repeat the new password'), 'different')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText('At least 12 characters.')).toBeInTheDocument()
    expect(screen.getByText('The passwords do not match.')).toBeInTheDocument()
  })

  it('shows the server error for a wrong current password', async () => {
    server.use(
      http.post('*/api/v1/auth/password/change', () =>
        problem(422, 'validation.failed', {
          errors: [{ field: 'current_password', code: 'password.current_incorrect' }],
        }),
      ),
    )
    await renderApp('/profile')
    await userEvent.type(await screen.findByLabelText('Current password'), 'Wrong-Password-1')
    await userEvent.type(screen.getByLabelText('New password'), 'Winter-Harbour-Compass-77')
    await userEvent.type(
      screen.getByLabelText('Repeat the new password'),
      'Winter-Harbour-Compass-77',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText('The current password is wrong.')).toBeInTheDocument()
  })
})
