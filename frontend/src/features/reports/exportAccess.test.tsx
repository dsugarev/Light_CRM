import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import {
  ADMIN_ME,
  MANAGER_ME,
  opportunityLists,
  page,
  REP_ME,
  signedInAs,
  VIEWER_ME,
} from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

// FR-REP-02 with the role matrix (requirements section 4, API spec 14): Viewers don't
// export; a Sales Rep's export holds only their own records, and the screen says so.

beforeEach(() => {
  server.use(
    http.get('*/api/v1/organizations', () => HttpResponse.json(page([]))),
    http.get('*/api/v1/reference/industries', () => HttpResponse.json([])),
  )
})

async function exportGroup() {
  await screen.findByRole('heading', { name: 'Organizations' })
  return screen.queryByRole('group', { name: 'Export' })
}

describe('FR-REP-02 who may export (2026-11-22)', () => {
  it('FR-REP-02 a Viewer sees no export buttons', async () => {
    signedInAs(VIEWER_ME)
    await renderApp('/organizations')
    expect(await exportGroup()).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Export XLSX' })).not.toBeInTheDocument()
  })

  it('FR-REP-02 a Sales Rep is told the export holds only their records', async () => {
    signedInAs(REP_ME)
    await renderApp('/organizations')
    await exportGroup()
    const group = screen.getByRole('group', { name: 'Export' })
    expect(group).toHaveAccessibleDescription('Your records only')
    expect(within(group).getByRole('button', { name: 'Export CSV' })).toBeVisible()
  })

  it.each([
    ['Sales Manager', MANAGER_ME],
    ['Admin', ADMIN_ME],
  ])('FR-REP-02 a %s exports without the own-records note', async (_, me) => {
    signedInAs(me)
    await renderApp('/organizations')
    const group = await exportGroup()
    expect(group).toBeInTheDocument()
    expect(screen.queryByText('Your records only')).not.toBeInTheDocument()
  })
})

describe('FR-OPP-03 board help for read-only users (2026-11-22)', () => {
  const board = { columns: [], truncated: false }

  it('FR-OPP-03 a Viewer gets reading help, not drag instructions', async () => {
    opportunityLists()
    server.use(http.get('*/api/v1/opportunities/board', () => HttpResponse.json(board)))
    signedInAs(VIEWER_ME)
    await renderApp('/opportunities/board')
    expect(await screen.findByText(/^Open deals by stage/)).toBeInTheDocument()
    expect(screen.queryByText(/^Drag a card/)).not.toBeInTheDocument()
  })

  it('FR-OPP-03 a Sales Rep gets the drag instructions', async () => {
    opportunityLists()
    server.use(http.get('*/api/v1/opportunities/board', () => HttpResponse.json(board)))
    signedInAs(REP_ME)
    await renderApp('/opportunities/board')
    expect(await screen.findByText(/^Drag a card/)).toBeInTheDocument()
  })
})
