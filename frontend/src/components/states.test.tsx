import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router'

import { ApiError } from '@/api/client'
import { createQueryClient } from '@/app/queryClient'
import { RouteError } from '@/app/RouteError'
import { LEAD, page, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

import { reloadPage } from '@/lib/reload'

import { Loading } from './Loading'

vi.mock('@/lib/reload', () => ({ reloadPage: vi.fn() }))

// UX-04: loading, empty and error states come from the shared components only.
const sources = import.meta.glob<string>(
  ['/src/**/*.tsx', '!/src/**/*.test.tsx', '!/src/test/**'],
  { query: '?raw', import: 'default', eager: true },
)

describe('UX-04 loading, empty and error states', () => {
  it('UX-04 no page writes its own loading or empty text', () => {
    const offenders = Object.entries(sources)
      .filter(([file]) => !file.startsWith('/src/components/'))
      .filter(([, text]) => /states\.(loading|empty)/.test(text))
      .map(([file]) => file)
    expect(offenders).toEqual([])
  })

  it.each(['page', 'table', 'form'] as const)(
    'UX-04 %s skeleton is announced once, without visible text',
    (variant) => {
      render(<Loading variant={variant} />)
      expect(screen.getByRole('status', { name: 'Loading…' })).toBeInTheDocument()
      expect(screen.queryByText('Loading…')).not.toBeInTheDocument()
    },
  )

  it('UX-04 an empty list shows the empty state', async () => {
    signedInAs(REP_ME)
    server.use(http.get('*/api/v1/leads', () => HttpResponse.json(page([]))))
    await renderApp('/leads')
    expect(await screen.findByText('Nothing to show.')).toBeInTheDocument()
  })

  it('UX-04 a failed list shows the request ID and retries', async () => {
    signedInAs(REP_ME)
    let calls = 0
    server.use(
      http.get('*/api/v1/leads', () => {
        calls += 1
        return calls === 1
          ? problem(500, 'server.internal_error', { request_id: 'req-4b1d' })
          : HttpResponse.json(page([LEAD]))
      }),
    )
    await renderApp('/leads')
    expect(
      await screen.findByText('Something went wrong on the server. Please try again.'),
    ).toBeInTheDocument()
    expect(screen.getByText('req-4b1d')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('link', { name: LEAD.title })).toBeInTheDocument()
  })

  it('UX-04 the route error boundary offers a retry and the request ID, in Bulgarian too', async () => {
    const { default: i18n } = await import('@/i18n')
    await i18n.changeLanguage('bg')
    function Broken(): never {
      throw new ApiError(500, { code: 'server.internal_error', request_id: 'req-route-7' })
    }
    const router = createMemoryRouter([
      { path: '/', element: <Broken />, errorElement: <RouteError /> },
    ])
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('req-route-7')
    await userEvent.click(screen.getByRole('button', { name: 'Опитай отново' }))
    expect(reloadPage).toHaveBeenCalledOnce()
  })
})
