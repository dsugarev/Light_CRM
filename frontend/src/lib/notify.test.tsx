import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http } from 'msw'
import { Toaster } from 'sonner'

import { ApiError } from '@/api/client'
import i18n from '@/i18n'
import { ADMIN_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

import { useNotify } from './notify'

function Trigger({ error, message }: { error?: unknown; message?: string }) {
  const notify = useNotify()
  return (
    <button
      type="button"
      onClick={() => {
        if (message) notify.success(message)
        else notify.error(error)
      }}
    >
      go
    </button>
  )
}

async function show(props: { error?: unknown; message?: string }) {
  render(
    <>
      <Trigger {...props} />
      <Toaster />
    </>,
  )
  await userEvent.click(screen.getByRole('button', { name: 'go' }))
}

describe('UX-05 feedback', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('UX-05 maps a backend error code to its translated message', async () => {
    await show({ error: new ApiError(409, { code: 'conflict.duplicate' }) })
    expect(
      await screen.findByText('A record with these details already exists.'),
    ).toBeInTheDocument()
  })

  it('UX-05 falls back to a generic message for unknown codes and network failures', async () => {
    await show({ error: new ApiError(418, { code: 'teapot.unknown' }) })
    await userEvent.click(screen.getByRole('button', { name: 'go' }))
    await waitFor(() => {
      expect(screen.getAllByText('Something went wrong. Please try again.')).toHaveLength(2)
    })
  })

  it('UX-05 maps the code in Bulgarian too', async () => {
    await i18n.changeLanguage('bg')
    await show({ error: new TypeError('Failed to fetch') })
    expect(await screen.findByText(i18n.t('errors:unknown'))).toBeInTheDocument()
  })

  it('UX-05 shows success messages', async () => {
    await show({ message: 'Saved.' })
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
  })

  it('UX-05 says when the language could not be kept on the profile', async () => {
    signedInAs(ADMIN_ME)
    server.use(http.patch('*/api/v1/me', () => problem(500, 'server.internal_error')))
    await renderApp('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Account menu: Ada Admin' }))
    await userEvent.click(await screen.findByRole('menuitemradio', { name: 'Български' }))
    // The profile still says English, so the screen returns to English and says why.
    expect(
      await screen.findByText('Something went wrong on the server. Please try again.'),
    ).toBeInTheDocument()
    expect(i18n.language).toBe('en')
  })
})
