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
    user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
    current: true,
  },
  {
    id: 's2',
    created_at: '2026-11-16T07:00:00Z',
    last_seen_at: '2026-11-16T08:00:00Z',
    expires_at: '2026-11-23T07:00:00Z',
    ip: '10.0.0.2',
    user_agent:
      'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1',
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

describe('FN-01 change password', () => {
  function rule(name: RegExp): HTMLElement {
    const list = screen.getByRole('list', { name: 'Password rules' })
    const text = within(list).getByText(name)
    return text.closest('li') ?? text
  }

  it('FN-01 shows the password rules live while typing', async () => {
    await renderApp('/profile')
    const next = await screen.findByLabelText('New password')
    expect(rule(/At least 12 characters/)).toHaveTextContent('(not yet)')
    await userEvent.type(next, 'Winter-Harbour-77')
    expect(rule(/At least 12 characters/)).toHaveTextContent('(done)')
    await userEvent.type(screen.getByLabelText('Repeat the new password'), 'Winter-Harbour-77')
    expect(rule(/Both entries match/)).toHaveTextContent('(done)')
    // Each of the three password fields can be shown.
    expect(screen.getAllByRole('button', { name: 'Show password', pressed: false })).toHaveLength(3)
  })

  it('FN-01 changes the password and says the other sessions were signed out', async () => {
    let body: unknown
    let sessionLoads = 0
    server.use(
      http.post('*/api/v1/auth/password/change', async ({ request }) => {
        body = await request.json()
        return new HttpResponse(null, { status: 204 })
      }),
      http.get('*/api/v1/me/sessions', () => {
        sessionLoads += 1
        // After the change only this session is left.
        return HttpResponse.json(sessionLoads === 1 ? sessions : sessions.slice(0, 1))
      }),
    )
    await renderApp('/profile')
    await userEvent.type(await screen.findByLabelText('Current password'), 'Old-Password-123')
    await userEvent.type(screen.getByLabelText('New password'), 'Winter-Harbour-77')
    await userEvent.type(screen.getByLabelText('Repeat the new password'), 'Winter-Harbour-77')
    await userEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(
      await screen.findByText('Password changed. Your other sessions were signed out.'),
    ).toBeInTheDocument()
    expect(body).toEqual({
      current_password: 'Old-Password-123',
      new_password: 'Winter-Harbour-77',
    })
    // The sessions list is reloaded and shows only this session.
    expect(await screen.findByText('This session')).toBeInTheDocument()
    expect(screen.queryByText('Safari on iOS')).not.toBeInTheDocument()
    expect(screen.getByLabelText('New password')).toHaveValue('')
  })
})

describe('FN-02 my sessions', () => {
  it('FN-02 lists device, start and last activity, with only the others revocable', async () => {
    await renderApp('/profile')
    const table = await screen.findByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    const [current, other] = rows as [HTMLElement, HTMLElement]
    expect(current).toHaveTextContent('Firefox on Windows')
    expect(current).toHaveTextContent('17 Nov 2026, 09:00') // signed in, Sofia time
    expect(current).toHaveTextContent('17 Nov 2026, 10:00') // last activity
    expect(within(current).getByText('This session')).toBeInTheDocument()
    expect(within(current).queryByRole('button')).not.toBeInTheDocument()
    expect(other).toHaveTextContent('Safari on iOS')
    expect(within(other).getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    // The full user-agent string stays available on hover.
    expect(within(other).getByText('Safari on iOS')).toHaveAttribute(
      'title',
      expect.stringContaining('iPhone OS 18_1') as string,
    )
  })

  it('FN-02 names the browser in Bulgarian too', async () => {
    signedInAs({ ...REP_ME, locale: 'bg' })
    await renderApp('/profile', 'bg')
    expect(await screen.findByText('Firefox на Windows')).toBeInTheDocument()
  })
})
