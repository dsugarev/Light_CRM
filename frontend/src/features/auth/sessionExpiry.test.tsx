import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { LEAD, page, REP_ME, referenceLists } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

import { signInAfterUnauthorized } from './sessionExpiry'

/** Signed in until `expire()`; then every request answers 401 until signing in again. */
function session() {
  let active = true
  server.use(
    http.get('*/api/v1/me', () =>
      active ? HttpResponse.json(REP_ME) : problem(401, 'auth.session_expired'),
    ),
    http.get('*/api/v1/leads', () =>
      active ? HttpResponse.json(page([LEAD])) : problem(401, 'auth.session_expired'),
    ),
    http.post('*/api/v1/auth/login', () => {
      active = true
      return HttpResponse.json({
        user: { id: REP_ME.id, full_name: REP_ME.full_name, role: 'sales_rep', locale: 'en' },
      })
    }),
  )
  return {
    expire: () => {
      active = false
    },
  }
}

describe('FN-04 session expiry', () => {
  beforeEach(() => {
    referenceLists()
  })

  it('FN-04 a lost session goes to sign-in, says so, and comes back after signing in', async () => {
    const { expire } = session()
    const { router, queryClient } = await renderApp('/leads?status=new')
    expect(await screen.findByRole('link', { name: LEAD.title })).toBeInTheDocument()

    expire()
    await queryClient.invalidateQueries({ queryKey: ['leads'] })
    expect(
      await screen.findByText('Your session has ended. Sign in again to continue where you were.'),
    ).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/sign-in')
    expect(new URLSearchParams(router.state.location.search).get('next')).toBe('/leads?status=new')

    await userEvent.type(screen.getByLabelText('Email'), 'boris.rep@example.test')
    await userEvent.type(screen.getByLabelText('Password'), 'Tuesday-Orchard-Lantern-42')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => {
      expect(router.state.location.pathname + router.state.location.search).toBe(
        '/leads?status=new',
      )
    })
  })

  it('FN-04 a first visit is sent to sign-in without the expiry message', async () => {
    const { router } = await renderApp('/leads')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(router.state.location.search).toBe('?next=%2Fleads')
    expect(screen.queryByText(/Your session has ended/)).not.toBeInTheDocument()
  })

  it('FN-04 unsaved changes do not hold back the move to sign-in', async () => {
    const { expire } = session()
    server.use(
      http.get('*/api/v1/organizations/duplicate-check', () => HttpResponse.json({ matches: [] })),
    )
    const { router, queryClient } = await renderApp('/leads/new')
    await userEvent.type(await screen.findByLabelText('Title'), 'Half-typed lead')
    expire()
    await queryClient.invalidateQueries({ queryKey: ['me'] })
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/sign-in')
    })
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('FN-04 the sign-in target keeps the page and only flags a lost session', () => {
    expect(signInAfterUnauthorized({ pathname: '/leads', search: '?q=a' }, true)).toBe(
      '/sign-in?next=%2Fleads%3Fq%3Da&expired=1',
    )
    expect(signInAfterUnauthorized({ pathname: '/leads', search: '' }, false)).toBe(
      '/sign-in?next=%2Fleads',
    )
    expect(signInAfterUnauthorized({ pathname: '/sign-in', search: '?next=%2F' }, true)).toBe(
      '/sign-in?next=%2F',
    )
  })
})
