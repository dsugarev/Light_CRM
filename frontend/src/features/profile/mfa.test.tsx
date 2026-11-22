import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ADMIN_ME, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

// FR-AUTH-07: optional two-factor sign-in, enforceable for Admins.

const SETUP = {
  secret: 'JBSWY3DPEHPK3PXP',
  provisioning_uri: 'otpauth://totp/Light%20CRM:boris.rep%40example.test?secret=JBSWY3DPEHPK3PXP',
}

beforeEach(() => {
  server.use(http.get('*/api/v1/me/sessions', () => HttpResponse.json([])))
})

describe('FR-AUTH-07 sign-in with a code', () => {
  it('asks for the code after the password and signs in with it', async () => {
    let signedIn = false
    let sentCode: unknown = null
    server.use(
      http.get('*/api/v1/me', () =>
        signedIn ? HttpResponse.json(REP_ME) : problem(401, 'auth.session_expired'),
      ),
      http.post('*/api/v1/auth/login', () => problem(401, 'auth.mfa_required')),
      http.post('*/api/v1/auth/login/mfa', async ({ request }) => {
        sentCode = await request.json()
        signedIn = true
        return HttpResponse.json({
          user: { id: REP_ME.id, full_name: REP_ME.full_name, role: 'sales_rep', locale: 'en' },
        })
      }),
    )
    const { router } = await renderApp('/sign-in')
    await userEvent.type(await screen.findByLabelText('Email'), 'boris.rep@example.test')
    await userEvent.type(screen.getByLabelText('Password'), 'Tuesday-Orchard-Lantern-42')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: 'Two-factor sign-in' })).toBeInTheDocument()
    const code = screen.getByLabelText('Code')
    expect(code).toHaveAttribute('autocomplete', 'one-time-code')
    await userEvent.type(code, '123456')
    await userEvent.click(screen.getByRole('button', { name: 'Verify' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/')
    })
    expect(sentCode).toEqual({ code: '123456' })
  })

  it('shows a wrong code and goes back to the password when the step expired', async () => {
    let attempts = 0
    server.use(
      http.post('*/api/v1/auth/login', () => problem(401, 'auth.mfa_required')),
      http.post('*/api/v1/auth/login/mfa', () => {
        attempts += 1
        return attempts === 1
          ? problem(401, 'auth.mfa_code_invalid')
          : problem(401, 'auth.session_expired')
      }),
    )
    await renderApp('/sign-in')
    await userEvent.type(await screen.findByLabelText('Email'), 'boris.rep@example.test')
    await userEvent.type(screen.getByLabelText('Password'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await userEvent.type(await screen.findByLabelText('Code'), '000000')
    await userEvent.click(screen.getByRole('button', { name: 'Verify' }))
    expect(await screen.findByText(/The code is wrong or has expired/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Verify' }))
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })
})

describe('FR-AUTH-07 profile', () => {
  it('sets up with a QR code and a key, then shows the recovery codes once', async () => {
    let me = { ...REP_ME }
    let confirmed: unknown = null
    server.use(
      http.get('*/api/v1/me', () => HttpResponse.json(me)),
      http.post('*/api/v1/auth/mfa/setup', () => HttpResponse.json(SETUP)),
      http.post('*/api/v1/auth/mfa/confirm', async ({ request }) => {
        confirmed = await request.json()
        me = { ...me, mfa_enabled: true }
        return HttpResponse.json({ recovery_codes: ['abcde-12345', 'fghij-67890'] })
      }),
    )
    await renderApp('/profile')
    const title = await screen.findByText('Two-factor sign-in')
    const card = title.closest<HTMLElement>('[data-slot="card"]')
    if (!card) throw new Error('The two-factor card is missing')
    expect(within(card).getByText('Off')).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: 'Set up two-factor sign-in' }))

    const form = await within(card).findByRole('form', { name: 'Set up two-factor sign-in' })
    expect(within(form).getByTitle('QR code for the authenticator app')).toBeInTheDocument()
    expect(within(form).getByText(SETUP.secret)).toBeInTheDocument()
    const turnOn = within(form).getByRole('button', { name: 'Turn on' })
    expect(turnOn).toBeDisabled()
    await userEvent.type(within(form).getByLabelText('Code from the app'), '654321')
    await userEvent.click(turnOn)

    const codes = await within(card).findByRole('region', { name: 'Recovery codes' })
    expect(within(codes).getByText('abcde-12345')).toBeInTheDocument()
    expect(confirmed).toEqual({ code: '654321' })
    expect(await within(card).findByText('On')).toBeInTheDocument()
    await userEvent.click(within(codes).getByRole('button', { name: 'I have saved them' }))
    expect(within(card).queryByText('abcde-12345')).not.toBeInTheDocument()
  })

  it('turns off with the password and shows an enforcement refusal', async () => {
    server.use(
      http.get('*/api/v1/me', () => HttpResponse.json({ ...REP_ME, mfa_enabled: true })),
      http.post('*/api/v1/auth/mfa/disable', () => problem(403, 'auth.mfa_enforced')),
    )
    await renderApp('/profile')
    const form = await screen.findByRole('form', { name: 'Turn off two-factor sign-in' })
    await userEvent.type(within(form).getByLabelText('Password'), 'secret')
    await userEvent.click(within(form).getByRole('button', { name: 'Turn off' }))
    expect(
      await within(form).findByText(/required for Admins and cannot be turned off/),
    ).toBeInTheDocument()
  })

  it('sends an Admin who must set it up to the profile, with only the setup card', async () => {
    signedInAs({ ...ADMIN_ME, mfa_setup_required: true })
    const { router } = await renderApp('/admin/users')
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/profile')
    })
    expect(await screen.findByText(/requires two-factor sign-in for Admins/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Set up two-factor sign-in' })).toBeInTheDocument()
    expect(screen.queryByText('Change password')).not.toBeInTheDocument()
  })
})

describe('FR-AUTH-07 Admin setting', () => {
  it('requires two-factor sign-in for Admins', async () => {
    signedInAs(ADMIN_ME)
    const current = {
      session_idle_timeout_minutes: 480,
      session_absolute_timeout_minutes: 10080,
      stale_opportunity_days: 14,
      mfa_required_for_admins: false,
      ai_model: 'gpt-oss-120b',
    }
    let saved: unknown = null
    server.use(
      http.get('*/api/v1/settings', () => HttpResponse.json(current)),
      http.patch('*/api/v1/settings', async ({ request }) => {
        saved = await request.json()
        return HttpResponse.json({ ...current, mfa_required_for_admins: true })
      }),
    )
    await renderApp('/admin/settings')
    await userEvent.click(
      await screen.findByRole('checkbox', { name: /Require two-factor sign-in for Admins/ }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      expect(saved).toMatchObject({ mfa_required_for_admins: true })
    })
  })
})
