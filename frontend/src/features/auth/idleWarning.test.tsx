import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { REP_ME } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

import { ACTIVITY_KEY, idleSchedule, SIGNED_OUT_KEY } from './sessionActivity'

const MINUTE = 60_000
const SESSION = { idle_timeout_minutes: 30, expires_at: '2099-01-01T00:00:00Z' }

/** Signed in with a 30-minute idle timeout; counts GET /me and logout calls. */
function signedIn() {
  const calls = { me: 0, logout: 0 }
  let active = true
  server.use(
    http.get('*/api/v1/me', () => {
      calls.me += 1
      return active
        ? HttpResponse.json({ ...REP_ME, session: SESSION })
        : HttpResponse.json({ code: 'auth.session_expired' }, { status: 401 })
    }),
    http.post('*/api/v1/auth/logout', () => {
      calls.logout += 1
      active = false
      return new HttpResponse(null, { status: 204 })
    }),
  )
  return calls
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe('FN-05 idle-timeout warning', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('FN-05 the schedule counts from a minute before the last request and respects the absolute expiry', () => {
    const at = Date.parse('2026-11-18T10:00:00Z')
    expect(idleSchedule(at, 30, '2099-01-01T00:00:00Z')).toEqual({
      deadline: at + 29 * MINUTE,
      warnAt: at + 24 * MINUTE,
    })
    expect(idleSchedule(at, 480, '2026-11-18T11:00:00Z').deadline).toBe(at + 60 * MINUTE)
  })

  it('FN-05 warns five minutes before the timeout and stays signed in', async () => {
    const calls = signedIn()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await renderApp('/')
    await screen.findByRole('heading', { name: 'Welcome, Boris Rep' })
    await advance(23 * MINUTE)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await advance(1 * MINUTE + 1000)
    const dialog = await screen.findByRole('alertdialog', { name: 'Still there?' })
    expect(dialog).toHaveTextContent(/signed out in (5:00|4:5\d) because of inactivity/)
    const before = calls.me
    await user.click(within(dialog).getByRole('button', { name: 'Stay signed in' }))
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    })
    expect(calls.me).toBe(before + 1)
    // The deadline moved: no warning again until 24 minutes later.
    await advance(23 * MINUTE)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(calls.logout).toBe(0)
  })

  it('FN-05 activity in another tab closes the warning', async () => {
    signedIn()
    await renderApp('/')
    await screen.findByRole('heading', { name: 'Welcome, Boris Rep' })
    await advance(24 * MINUTE + 1000)
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', { key: ACTIVITY_KEY, newValue: String(Date.now()) }),
      )
    })
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    })
  })

  it('FN-05 without an answer the session ends and sign-in says why', async () => {
    const calls = signedIn()
    const { router } = await renderApp('/leads')
    await screen.findByRole('heading', { level: 1, name: 'Leads' })
    await advance(29 * MINUTE + 1000)
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/sign-in')
    })
    expect(calls.logout).toBe(1)
    expect(
      await screen.findByText('Your session has ended. Sign in again to continue where you were.'),
    ).toBeInTheDocument()
    expect(new URLSearchParams(router.state.location.search).get('next')).toBe('/leads')
  })

  it('FN-05 signing out from the warning tells the other tabs', async () => {
    const calls = signedIn()
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    const { router } = await renderApp('/')
    await screen.findByRole('heading', { name: 'Welcome, Boris Rep' })
    await advance(24 * MINUTE + 1000)
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Sign out' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/sign-in')
    })
    expect(calls.logout).toBe(1)
    expect(localStorage.getItem(SIGNED_OUT_KEY)).not.toBeNull()
    expect(screen.queryByText(/Your session has ended/)).not.toBeInTheDocument()
  })

  it('FN-05 a sign-out in another tab signs this tab out too, in Bulgarian', async () => {
    signedIn()
    server.use(
      http.get('*/api/v1/me', () =>
        HttpResponse.json({ ...REP_ME, locale: 'bg', session: SESSION }),
      ),
    )
    const { router } = await renderApp('/', 'bg')
    await screen.findByRole('heading', { name: 'Добре дошли, Boris Rep' })
    server.use(
      http.get('*/api/v1/me', () =>
        HttpResponse.json({ code: 'auth.session_expired' }, { status: 401 }),
      ),
    )
    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', { key: SIGNED_OUT_KEY, newValue: String(Date.now()) }),
      )
    })
    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/sign-in')
  })
})
