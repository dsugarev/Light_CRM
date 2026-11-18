import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'

import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

async function fill(email = 'x@example.test', password = 'whatever') {
  await userEvent.type(await screen.findByLabelText('Email'), email)
  await userEvent.type(screen.getByLabelText('Password'), password)
}

describe('UX-06 sign-in page', () => {
  it('UX-06 uses the autocomplete hints password managers expect', async () => {
    await renderApp('/sign-in')
    expect(await screen.findByLabelText('Email')).toHaveAttribute('autocomplete', 'username')
    expect(screen.getByLabelText('Password')).toHaveAttribute('autocomplete', 'current-password')
    expect(screen.getByRole('button', { name: 'Български' })).toBeInTheDocument()
  })

  it('UX-06 shows and hides the password', async () => {
    await renderApp('/sign-in')
    const password = await screen.findByLabelText('Password')
    expect(password).toHaveAttribute('type', 'password')
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password).toHaveAttribute('type', 'text')
    const hide = screen.getByRole('button', { name: 'Hide password' })
    expect(hide).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(hide)
    expect(password).toHaveAttribute('type', 'password')
  })

  it('UX-06 shows caps lock warning', async () => {
    await renderApp('/sign-in')
    const password = await screen.findByLabelText('Password')
    await userEvent.click(password)
    await userEvent.keyboard('{CapsLock}a')
    expect(await screen.findByText('Caps Lock is on.')).toBeInTheDocument()
    expect(password.getAttribute('aria-describedby')).toContain(
      screen.getByText('Caps Lock is on.').id,
    )
    // Leaving the field clears the warning; the next key press there checks again.
    await userEvent.tab()
    expect(screen.queryByText('Caps Lock is on.')).not.toBeInTheDocument()
  })

  it('UX-06 disables the button with a spinner while signing in', async () => {
    server.use(
      http.post('*/api/v1/auth/login', async () => {
        await delay('infinite')
        return HttpResponse.json({})
      }),
    )
    await renderApp('/sign-in')
    await fill()
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    const busy = await screen.findByRole('button', { name: 'Signing in…' })
    expect(busy).toBeDisabled()
    expect(busy).toHaveAttribute('aria-busy', 'true')
  })

  it('UX-06 says how long a lockout lasts and focuses the message', async () => {
    const lockedUntil = new Date(Date.now() + 14.5 * 60_000).toISOString()
    server.use(
      http.post('*/api/v1/auth/login', () =>
        problem(423, 'auth.account_locked', { locked_until: lockedUntil }),
      ),
    )
    await renderApp('/sign-in')
    await fill()
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The account is locked until')
    await waitFor(() => {
      expect(alert).toHaveFocus()
    })
    expect(screen.getByText('You can try again in 15 minutes.')).toBeInTheDocument()
  })

  it('UX-06 moves focus to the first field with an error', async () => {
    await renderApp('/sign-in')
    await userEvent.type(await screen.findByLabelText('Password'), 'whatever')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => {
      expect(screen.getByLabelText('Email')).toHaveFocus()
    })
  })

  it('UX-06 shows the lockout time in Bulgarian too', async () => {
    const lockedUntil = new Date(Date.now() + 60_000).toISOString()
    server.use(
      http.post('*/api/v1/auth/login', () =>
        problem(423, 'auth.account_locked', { locked_until: lockedUntil }),
      ),
    )
    await renderApp('/sign-in', 'bg')
    await userEvent.type(await screen.findByLabelText('Имейл'), 'x@example.test')
    await userEvent.type(screen.getByLabelText('Парола'), 'whatever')
    await userEvent.click(screen.getByRole('button', { name: 'Вход' }))
    expect(await screen.findByText('Можете да опитате отново след 1 минута.')).toBeInTheDocument()
  })
})
