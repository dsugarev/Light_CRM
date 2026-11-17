import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '@/test/server'
import { renderApp } from '@/test/render'

describe('app shell', () => {
  it('redirects the start page to the sign-in placeholder', async () => {
    const { router } = await renderApp('/')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/sign-in')
  })

  it('keeps the sign-in form disabled until authentication exists', async () => {
    await renderApp('/sign-in')
    expect(await screen.findByLabelText('Email')).toBeDisabled()
    expect(screen.getByLabelText('Password')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled()
  })

  it('FR-I18N-01 shows the sign-in page in Bulgarian', async () => {
    await renderApp('/sign-in', 'bg')
    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
    expect(screen.getByLabelText('Парола')).toBeInTheDocument()
  })

  it('FR-I18N-01 switches language from the header and remembers it', async () => {
    await renderApp('/sign-in')
    await userEvent.click(await screen.findByRole('button', { name: 'Български' }))
    expect(await screen.findByRole('heading', { name: 'Вход' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Български' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(document.documentElement.lang).toBe('bg')
    expect(localStorage.getItem('crm.locale')).toBe('bg')
  })

  it('shows a translated not-found message for unknown pages', async () => {
    await renderApp('/does-not-exist')
    expect(await screen.findByRole('alert')).toHaveTextContent('This page does not exist.')
  })

  it('NFR-08 shows the API as online when the readiness check passes', async () => {
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
