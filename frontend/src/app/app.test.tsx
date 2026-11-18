import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ADMIN_ME, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

describe('app shell and sign-in', () => {
  it('FR-AUTH-01 sends anonymous visitors to sign-in and remembers where they were going', async () => {
    const { router } = await renderApp('/profile')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/sign-in')
    expect(router.state.location.search).toBe('?next=%2Fprofile')
  })

  it('FR-AUTH-01 AC1 signs in and returns to the requested page', async () => {
    let body: unknown
    server.use(
      http.post('*/api/v1/auth/login', async ({ request }) => {
        body = await request.json()
        signedInAs(REP_ME)
        return HttpResponse.json({
          user: { id: REP_ME.id, full_name: REP_ME.full_name, role: 'sales_rep', locale: 'en' },
        })
      }),
    )
    const { router } = await renderApp('/sign-in?next=%2Fprofile')
    await userEvent.type(await screen.findByLabelText('Email'), 'boris.rep@example.test')
    await userEvent.type(screen.getByLabelText('Password'), 'Tuesday-Orchard-Lantern-42')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'My profile' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/profile')
    expect(body).toEqual({
      email: 'boris.rep@example.test',
      password: 'Tuesday-Orchard-Lantern-42',
    })
  })

  it('FR-AUTH-01 AC2 shows a generic message for wrong credentials', async () => {
    server.use(http.post('*/api/v1/auth/login', () => problem(401, 'auth.invalid_credentials')))
    await renderApp('/sign-in')
    await userEvent.type(await screen.findByLabelText('Email'), 'x@example.test')
    await userEvent.type(screen.getByLabelText('Password'), 'whatever')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong email or password.')
  })

  it('FR-AUTH-01 AC3 shows when a locked account opens again, in Sofia time', async () => {
    server.use(
      http.post('*/api/v1/auth/login', () =>
        problem(423, 'auth.account_locked', { locked_until: '2026-11-17T09:15:00+00:00' }),
      ),
    )
    await renderApp('/sign-in')
    await userEvent.type(await screen.findByLabelText('Email'), 'x@example.test')
    await userEvent.type(screen.getByLabelText('Password'), 'whatever')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('locked until 17 Nov 2026, 11:15')
  })

  it('validates required fields before calling the API', async () => {
    await renderApp('/sign-in')
    await userEvent.click(await screen.findByRole('button', { name: 'Sign in' }))
    expect(await screen.findAllByText('Required.')).toHaveLength(2)
  })

  it('FR-I18N-01 shows the sign-in page in Bulgarian', async () => {
    await renderApp('/sign-in', 'bg')
    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
    expect(screen.getByLabelText('Парола')).toBeInTheDocument()
  })

  it('FR-I18N-01 switches language before sign-in and remembers it locally', async () => {
    await renderApp('/sign-in')
    await userEvent.click(await screen.findByRole('button', { name: 'Български' }))
    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('bg')
    expect(localStorage.getItem('crm.locale')).toBe('bg')
  })

  it('FR-I18N-01 saves the language on the profile when signed in', async () => {
    signedInAs(ADMIN_ME)
    let saved: unknown
    server.use(
      http.patch('*/api/v1/me', async ({ request }) => {
        saved = await request.json()
        return HttpResponse.json({ ...ADMIN_ME, locale: 'bg' })
      }),
    )
    await renderApp('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Account menu: Ada Admin' }))
    await userEvent.click(await screen.findByRole('menuitemradio', { name: 'Български' }))
    await waitFor(() => {
      expect(saved).toEqual({ locale: 'bg' })
    })
    expect(
      await screen.findByRole('heading', { name: 'Добре дошли, Ada Admin' }),
    ).toBeInTheDocument()
  })

  it('FR-I18N-01 follows the language stored on the profile', async () => {
    signedInAs({ ...REP_ME, locale: 'bg' })
    await renderApp('/')
    expect(
      await screen.findByRole('heading', { name: 'Добре дошли, Boris Rep' }),
    ).toBeInTheDocument()
  })

  it('FR-AUTH-05 hides admin navigation from non-admins and keeps them out of admin pages', async () => {
    signedInAs(REP_ME)
    const { router } = await renderApp('/admin/users')
    expect(await screen.findByRole('heading', { name: 'Welcome, Boris Rep' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument()
  })

  it('shows admin navigation to admins', async () => {
    signedInAs(ADMIN_ME)
    await renderApp('/')
    expect(await screen.findByRole('link', { name: 'Users' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Audit log' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument()
  })

  it('FR-AUTH-04 signs out and returns to sign-in', async () => {
    signedInAs(ADMIN_ME)
    server.use(http.post('*/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })))
    const { router } = await renderApp('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Account menu: Ada Admin' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/sign-in')
  })

  it('shows a translated not-found message for unknown pages', async () => {
    await renderApp('/does-not-exist')
    expect(await screen.findByRole('alert')).toHaveTextContent('This page does not exist.')
  })

  it('NFR-08 shows the API as online or unavailable', async () => {
    await renderApp('/sign-in')
    await waitFor(() => {
      expect(screen.getByTestId('api-status')).toHaveTextContent('Online')
    })
  })

  it('NFR-08 shows the API as unavailable when the readiness check fails', async () => {
    server.use(
      http.get('*/api/health/ready', () =>
        HttpResponse.json({ status: 'unavailable' }, { status: 503 }),
      ),
    )
    await renderApp('/sign-in')
    await waitFor(() => {
      expect(screen.getByTestId('api-status')).toHaveTextContent('Unavailable')
    })
  })
})

describe('FN-06 language preference', () => {
  it('FN-06 signing in on another device applies the language saved on the profile', async () => {
    // This browser was last used in English; the profile says Bulgarian.
    localStorage.setItem('crm.locale', 'en')
    server.use(
      http.post('*/api/v1/auth/login', () => {
        signedInAs({ ...REP_ME, locale: 'bg' })
        return HttpResponse.json({
          user: { id: REP_ME.id, full_name: REP_ME.full_name, role: 'sales_rep', locale: 'bg' },
        })
      }),
    )
    await renderApp('/sign-in')
    await userEvent.type(await screen.findByLabelText('Email'), 'boris.rep@example.test')
    await userEvent.type(screen.getByLabelText('Password'), 'Tuesday-Orchard-Lantern-42')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(
      await screen.findByRole('heading', { name: 'Добре дошли, Boris Rep' }),
    ).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('bg')
    // Remembered on this device too, for the sign-in page next time.
    expect(localStorage.getItem('crm.locale')).toBe('bg')
  })
})
