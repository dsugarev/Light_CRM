import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

import { safeNext } from './safeNext'

describe('FR-AUTH-02 set password from a one-time link', () => {
  it('checks the token from the URL fragment and sets the password', async () => {
    let body: unknown
    server.use(
      http.get('*/api/v1/auth/password/token/:token', ({ params }) =>
        params['token'] === 'tok123'
          ? HttpResponse.json({ email: 'nova@example.test', purpose: 'set' })
          : problem(400, 'auth.token_invalid'),
      ),
      http.post('*/api/v1/auth/password/set', async ({ request }) => {
        body = await request.json()
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { router } = await renderApp('/set-password#token=tok123')
    expect(await screen.findByText('For nova@example.test')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('New password'), 'Winter-Harbour-Compass-77')
    await userEvent.type(
      screen.getByLabelText('Repeat the new password'),
      'Winter-Harbour-Compass-77',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(
      await screen.findByText('Your password is set. You can sign in now.'),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/sign-in')
    expect(body).toEqual({ token: 'tok123', password: 'Winter-Harbour-Compass-77' })
  })

  it('explains an invalid or used link', async () => {
    server.use(
      http.get('*/api/v1/auth/password/token/:token', () => problem(400, 'auth.token_invalid')),
    )
    await renderApp('/set-password#token=used')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This link is invalid, already used or expired.',
    )
  })

  it('shows the policy error returned by the server', async () => {
    server.use(
      http.get('*/api/v1/auth/password/token/:token', () =>
        HttpResponse.json({ email: 'n@example.test', purpose: 'reset' }),
      ),
      http.post('*/api/v1/auth/password/set', () =>
        problem(422, 'auth.password_policy', {
          errors: [{ field: 'password', code: 'password.too_common' }],
        }),
      ),
    )
    await renderApp('/set-password#token=t')
    expect(
      await screen.findByRole('heading', { name: 'Choose a new password' }),
    ).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('New password'), 'unbelievable')
    await userEvent.type(screen.getByLabelText('Repeat the new password'), 'unbelievable')
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }))
    expect(await screen.findByText('This password is too common.')).toBeInTheDocument()
  })
})

describe('forgot password', () => {
  it('always confirms without revealing whether the account exists', async () => {
    server.use(
      http.post('*/api/v1/auth/password/forgot', () => new HttpResponse(null, { status: 202 })),
    )
    await renderApp('/forgot-password')
    await userEvent.type(await screen.findByLabelText('Email'), 'anyone@example.test')
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByRole('status')).toHaveTextContent(
      'If an account exists for this address',
    )
  })
})

describe('safeNext', () => {
  it.each([
    ['/profile', '/profile'],
    ['/admin/users?role=viewer', '/admin/users?role=viewer'],
    ['https://evil.example', '/'],
    ['//evil.example', '/'],
    ['/\\evil.example', '/'],
    [null, '/'],
  ])('%s -> %s', (input, expected) => {
    expect(safeNext(input)).toBe(expected)
  })
})
