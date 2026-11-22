import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import {
  ADMIN_ME,
  OPPORTUNITY,
  opportunityLists,
  ORG,
  page,
  referenceLists,
  REP_ME,
  signedInAs,
  STAGES,
  summary,
  USER,
} from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

// Loop 3: interactivity as in leading CRMs: the sales path, clickable rows.

function must<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error('element not found')
  return value
}

function onOpportunity(opportunity = OPPORTUNITY) {
  opportunityLists()
  server.use(
    http.get(`*/api/v1/opportunities/${opportunity.id}`, () => HttpResponse.json(opportunity)),
    http.get(`*/api/v1/opportunities/${opportunity.id}/stage-history`, () => HttpResponse.json([])),
  )
}

describe('FR-OPP-02 sales path on the opportunity (loop 3)', () => {
  it('FR-OPP-02 shows the open stages in order with passed, current and upcoming steps', async () => {
    signedInAs(REP_ME)
    onOpportunity()
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    const path = await screen.findByRole('list', { name: 'Sales path' })
    const steps = within(path).getAllByRole('listitem')
    expect(steps.map((step) => step.textContent)).toEqual([
      '✓Prospecting(passed)',
      'Qualification',
      'Solution & Proposal',
      'Negotiation',
      'Closed',
    ])
    expect(steps[1]).toHaveAttribute('aria-current', 'step')
    expect(within(must(steps[1])).queryByRole('button')).not.toBeInTheDocument()
    expect(within(must(steps[1])).getByText('Qualification')).toHaveClass('bg-primary')
  })

  it('FR-OPP-02 clicking a stage moves the opportunity there with its version', async () => {
    signedInAs(REP_ME)
    onOpportunity()
    let body: Record<string, unknown> = {}
    let current = OPPORTUNITY
    server.use(
      http.get(`*/api/v1/opportunities/${OPPORTUNITY.id}`, () => HttpResponse.json(current)),
      http.post(`*/api/v1/opportunities/${OPPORTUNITY.id}/move`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        current = { ...OPPORTUNITY, stage: summary(STAGES[3]), version: 3 }
        return HttpResponse.json(current)
      }),
    )
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Move to Negotiation' }))
    await waitFor(() => {
      expect(body).toEqual({ stage_id: STAGES[3].id, version: 2 })
    })
    const path = screen.getByRole('list', { name: 'Sales path' })
    await waitFor(() => {
      expect(within(path).getAllByRole('listitem')[3]).toHaveAttribute('aria-current', 'step')
    })
  })

  it('FR-AUTH-05 a user who may not edit sees the path without stage buttons', async () => {
    signedInAs(REP_ME)
    onOpportunity({ ...OPPORTUNITY, owner: { id: USER.id, full_name: USER.full_name } })
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    const path = await screen.findByRole('list', { name: 'Sales path' })
    expect(within(path).queryAllByRole('button')).toHaveLength(0)
  })

  it('FR-OPP-05 a won opportunity has every stage passed and the outcome in green', async () => {
    signedInAs(REP_ME)
    onOpportunity({
      ...OPPORTUNITY,
      stage: summary(STAGES[4]),
      actual_close_date: '2026-11-20',
    })
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    const path = await screen.findByRole('list', { name: 'Sales path' })
    expect(within(path).getAllByText('(passed)')).toHaveLength(4)
    expect(within(path).queryAllByRole('button')).toHaveLength(0)
    const outcome = within(path).getByTestId('path-outcome')
    expect(outcome).toHaveTextContent('Closed Won')
    expect(outcome).toHaveClass('text-success')
    expect(outcome.closest('li')).toHaveAttribute('aria-current', 'step')
  })
})

describe('UX-08 clickable list rows (loop 3)', () => {
  beforeEach(() => {
    referenceLists()
    server.use(
      http.get('*/api/v1/organizations', () => HttpResponse.json(page([ORG]))),
      http.get(`*/api/v1/organizations/${ORG.id}`, () => HttpResponse.json(ORG)),
    )
  })

  it('UX-08 a click anywhere on a row opens the record', async () => {
    signedInAs(ADMIN_ME)
    const { router } = await renderApp('/organizations')
    const link = await screen.findByRole('link', { name: ORG.name })
    const row = must(link.closest('tr'))
    expect(row).toHaveClass('cursor-pointer')
    expect(row).toHaveAttribute('data-href', `/organizations/${ORG.id}`)
    const cells = within(row).getAllByRole('cell')
    await userEvent.click(must(cells[cells.length - 1]))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/organizations/${ORG.id}`)
    })
  })

  it('UX-08 Ctrl-click on a row opens the record in a new tab', async () => {
    signedInAs(ADMIN_ME)
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    const { router } = await renderApp('/organizations')
    const row = must((await screen.findByRole('link', { name: ORG.name })).closest('tr'))
    const user = userEvent.setup()
    await user.keyboard('{Control>}')
    await user.click(must(within(row).getAllByRole('cell')[1]))
    await user.keyboard('{/Control}')
    expect(open).toHaveBeenCalledWith(`/organizations/${ORG.id}`, '_blank', 'noopener')
    expect(router.state.location.pathname).toBe('/organizations')
    open.mockRestore()
  })

  it('UX-08 selecting text in a row does not navigate', async () => {
    signedInAs(ADMIN_ME)
    const { router } = await renderApp('/organizations')
    const row = must((await screen.findByRole('link', { name: ORG.name })).closest('tr'))
    const selection = vi
      .spyOn(window, 'getSelection')
      .mockReturnValue({ toString: () => 'Sofia' } as Selection)
    await userEvent.click(must(within(row).getAllByRole('cell')[1]))
    expect(router.state.location.pathname).toBe('/organizations')
    selection.mockRestore()
  })
})
