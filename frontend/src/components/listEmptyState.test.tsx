import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { page, referenceLists, REP_ME, signedInAs } from '@/test/fixtures'

const VIEWER_ME = { ...REP_ME, role: 'viewer' as const, permissions: ['records.read'] }
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

describe('empty lists say what to do next', () => {
  beforeEach(() => {
    referenceLists()
    server.use(http.get('*/api/v1/leads', () => HttpResponse.json(page([]))))
  })

  it('offers to create the first record', async () => {
    signedInAs(REP_ME)
    await renderApp('/leads')
    expect(await screen.findByText('There is nothing here yet.')).toBeInTheDocument()
    const create = screen.getAllByRole('link', { name: 'New lead' })
    // One in the page header, one in the empty state.
    expect(create).toHaveLength(2)
    expect(create[1]).toHaveAttribute('href', '/leads/new')
  })

  it('offers no create action to a user who may not create', async () => {
    signedInAs(VIEWER_ME)
    await renderApp('/leads')
    expect(await screen.findByText('There is nothing here yet.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'New lead' })).not.toBeInTheDocument()
  })

  it('clears search and filters but keeps the sort', async () => {
    signedInAs(REP_ME)
    const { router } = await renderApp('/leads?q=zzz&status=new&sort=title&page=2')
    expect(await screen.findByText('No records match the search or filters.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => {
      expect(router.state.location.search).toBe('?sort=title')
    })
    expect(await screen.findByText('There is nothing here yet.')).toBeInTheDocument()
    expect(screen.getByRole('searchbox', { name: /Search by title/ })).toHaveValue('')
  })

  it('says so in Bulgarian too', async () => {
    signedInAs({ ...REP_ME, locale: 'bg' })
    await renderApp('/leads?q=zzz', 'bg')
    expect(
      await screen.findByText('Няма записи, които отговарят на търсенето или филтрите.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Изчисти филтрите' })).toBeInTheDocument()
  })
})
