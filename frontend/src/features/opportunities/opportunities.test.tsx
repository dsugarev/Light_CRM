import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { Schemas } from '@/api/client'
import {
  ADMIN_ME,
  LOSS_REASON,
  OPPORTUNITY,
  opportunityLists,
  ORG,
  page,
  PIPELINE,
  REP_ME,
  signedInAs,
  STAGES,
  summary,
} from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

beforeEach(() => {
  opportunityLists()
})

function onOpportunity(opportunity = OPPORTUNITY) {
  server.use(
    http.get(`*/api/v1/opportunities/${opportunity.id}`, () => HttpResponse.json(opportunity)),
    http.get(`*/api/v1/opportunities/${opportunity.id}/stage-history`, () =>
      HttpResponse.json([
        {
          id: 'h-1',
          from_stage: null,
          to_stage: summary(STAGES[0]),
          changed_by: OPPORTUNITY.created_by,
          changed_at: '2026-11-17T08:00:00Z',
        },
        {
          id: 'h-2',
          from_stage: summary(STAGES[0]),
          to_stage: summary(STAGES[1]),
          changed_by: OPPORTUNITY.created_by,
          changed_at: '2026-11-17T09:00:00Z',
        },
      ]),
    ),
  )
}

const card = (overrides: Partial<Schemas['BoardCard']> = {}): Schemas['BoardCard'] => ({
  id: OPPORTUNITY.id,
  name: OPPORTUNITY.name,
  organization: OPPORTUNITY.organization,
  amount: '48000.00',
  expected_close_date: '2027-02-28',
  owner: OPPORTUNITY.owner,
  is_stale: false,
  can_edit: true,
  version: 2,
  ...overrides,
})

function onBoard(cards: Schemas['BoardCard'][] = [card()]) {
  const board: Schemas['Board'] = {
    pipeline_id: PIPELINE.id,
    currency: 'EUR',
    truncated: false,
    columns: STAGES.filter((s) => s.stage_type === 'open').map((s, index) => ({
      stage: summary(s),
      count: index === 1 ? cards.length : 0,
      total_amount: index === 1 ? '48000.00' : '0.00',
      weighted_amount: index === 1 ? '12000.00' : '0.00',
      cards: index === 1 ? cards : [],
    })),
  }
  server.use(http.get('*/api/v1/opportunities/board', () => HttpResponse.json(board)))
}

describe('FR-OPP-04 opportunity list', () => {
  it('shows stage, amounts and the stale flag, with filters in the URL', async () => {
    signedInAs(REP_ME)
    const requests: string[] = []
    server.use(
      http.get('*/api/v1/opportunities', ({ request }) => {
        requests.push(new URL(request.url).search)
        return HttpResponse.json(page([{ ...OPPORTUNITY, is_stale: true }]))
      }),
    )
    const { router } = await renderApp('/opportunities')
    const table = await screen.findByRole('table', { name: 'Opportunities' })
    expect(within(table).getByRole('link', { name: 'Branch connectivity' })).toBeInTheDocument()
    expect(within(table).getByText('Qualification')).toBeInTheDocument()
    expect(within(table).getByText('€48,000.00')).toBeInTheDocument()
    expect(within(table).getByText('€12,000.00')).toBeInTheDocument()
    expect(within(table).getByText('Needs attention')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'won')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Needs attention' }))
    await waitFor(() => {
      expect(router.state.location.search).toContain('stage_type=won')
    })
    expect(router.state.location.search).toContain('is_stale=true')
    await waitFor(() => {
      expect(requests.at(-1)).toContain('is_stale=true')
    })
  })
})

describe('FR-OPP-01 create', () => {
  it('requires an organization', async () => {
    signedInAs(REP_ME)
    await renderApp('/opportunities/new')
    await userEvent.type(await screen.findByLabelText('Name'), 'Branch connectivity')
    await userEvent.click(screen.getByRole('button', { name: 'Create opportunity' }))
    expect(await screen.findByText('Required.')).toBeInTheDocument()
  })

  it('creates for a preset organization; empty probability follows the stage', async () => {
    signedInAs(REP_ME)
    let body: Record<string, unknown> = {}
    server.use(
      http.get(`*/api/v1/organizations/${ORG.id}`, () =>
        HttpResponse.json({
          ...ORG,
          counts: {
            contacts: 0,
            open_leads: 0,
            open_opportunities: 0,
            open_pipeline_value: '0.00',
            currency: 'EUR',
          },
        }),
      ),
      http.get(`*/api/v1/organizations/${ORG.id}/contacts`, () => HttpResponse.json(page([]))),
      http.post('*/api/v1/opportunities', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(OPPORTUNITY, { status: 201 })
      }),
    )
    onOpportunity()
    const { router } = await renderApp(`/opportunities/new?organization_id=${ORG.id}`)
    await userEvent.type(await screen.findByLabelText('Name'), 'Branch connectivity')
    await userEvent.type(screen.getByLabelText('Amount (EUR)'), '48000,5')
    await userEvent.click(screen.getByRole('button', { name: 'Create opportunity' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/opportunities/${OPPORTUNITY.id}`)
    })
    expect(body).toMatchObject({
      name: 'Branch connectivity',
      organization_id: ORG.id,
      amount: '48000.5',
      probability: null,
    })
  })
})

describe('FR-OPP-02, 05 opportunity detail', () => {
  it('FR-OPP-02 moves to another open stage with the version and shows history', async () => {
    signedInAs(REP_ME)
    onOpportunity()
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`*/api/v1/opportunities/${OPPORTUNITY.id}/move`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...OPPORTUNITY, stage: summary(STAGES[3]), version: 3 })
      }),
    )
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    expect(await screen.findByText('Prospecting → Qualification')).toBeInTheDocument()
    const stage = screen.getByRole('combobox', { name: 'Stage' })
    expect(within(stage).queryByRole('option', { name: 'Closed Won' })).not.toBeInTheDocument()
    await userEvent.selectOptions(stage, STAGES[3].id)
    await userEvent.click(screen.getByRole('button', { name: 'Move' }))
    await waitFor(() => {
      expect(body).toEqual({ stage_id: STAGES[3].id, version: 2 })
    })
  })

  it('FR-OPP-05 closing as lost needs a loss reason', async () => {
    signedInAs(REP_ME)
    onOpportunity()
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`*/api/v1/opportunities/${OPPORTUNITY.id}/close`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...OPPORTUNITY,
          stage: summary(STAGES[5]),
          loss_reason: LOSS_REASON,
          actual_close_date: '2026-11-17',
          version: 3,
        })
      }),
    )
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Close as lost' }))
    const form = screen.getByRole('form', { name: 'Close as lost' })
    await userEvent.click(within(form).getByRole('button', { name: 'Close as lost' }))
    expect(await within(form).findByText('Choose a loss reason.')).toBeInTheDocument()
    await userEvent.selectOptions(within(form).getByLabelText('Loss reason'), LOSS_REASON.id)
    await userEvent.type(within(form).getByLabelText('Competitor'), 'Друг оператор')
    await userEvent.click(within(form).getByRole('button', { name: 'Close as lost' }))
    await waitFor(() => {
      expect(body).toEqual({
        outcome: 'lost',
        version: 2,
        loss_reason_id: LOSS_REASON.id,
        competitor: 'Друг оператор',
        actual_close_date: null,
      })
    })
  })

  it('FR-OPP-05 a closed opportunity is read-only; only a manager sees Reopen', async () => {
    const lost = {
      ...OPPORTUNITY,
      stage: summary(STAGES[5]),
      loss_reason: LOSS_REASON,
      actual_close_date: '2026-11-10',
    }
    signedInAs(REP_ME)
    onOpportunity(lost)
    const view = await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    expect(await screen.findByText('Lost on 10 Nov 2026: Price')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Move' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reopen' })).not.toBeInTheDocument()
    view.unmount()

    signedInAs(ADMIN_ME)
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`*/api/v1/opportunities/${OPPORTUNITY.id}/reopen`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...OPPORTUNITY, stage: summary(STAGES[3]), version: 3 })
      }),
    )
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    await userEvent.selectOptions(
      await screen.findByRole('combobox', { name: 'Reopen into stage' }),
      STAGES[3].id,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Reopen' }))
    await waitFor(() => {
      expect(body).toEqual({ stage_id: STAGES[3].id, version: 2 })
    })
  })

  it('shows the server version after a conflict', async () => {
    signedInAs(REP_ME)
    onOpportunity()
    server.use(
      http.post(`*/api/v1/opportunities/${OPPORTUNITY.id}/move`, () =>
        problem(409, 'conflict.version_mismatch', {
          current: { ...OPPORTUNITY, name: 'Renamed elsewhere', version: 5 },
        }),
      ),
    )
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    await userEvent.selectOptions(
      await screen.findByRole('combobox', { name: 'Stage' }),
      STAGES[2].id,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Move' }))
    expect(await screen.findByRole('heading', { name: 'Renamed elsewhere' })).toBeInTheDocument()
  })
})

describe('FR-OPP-03 pipeline board', () => {
  it('shows open stages with totals and moves a card with the keyboard alternative', async () => {
    signedInAs(REP_ME)
    onBoard()
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`*/api/v1/opportunities/${OPPORTUNITY.id}/move`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...OPPORTUNITY, stage: summary(STAGES[2]), version: 3 })
      }),
    )
    await renderApp('/opportunities/board')
    const column = await screen.findByRole('list', { name: 'Qualification' })
    expect(within(column).getByRole('link', { name: 'Branch connectivity' })).toBeInTheDocument()
    expect(screen.getByTestId(`totals-${STAGES[1].id}`)).toHaveTextContent(
      '1 opportunity · €48,000.00 · weighted €12,000.00',
    )
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Prospecting',
      'Qualification',
      'Solution & Proposal',
      'Negotiation',
    ])
    expect(screen.getByRole('button', { name: 'Drag Branch connectivity' })).toBeInTheDocument()
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Move Branch connectivity to' }),
      `stage:${STAGES[2].id}`,
    )
    await waitFor(() => {
      expect(body).toEqual({ stage_id: STAGES[2].id, version: 2 })
    })
  })

  it('dropping on Lost asks for a loss reason; won closes directly', async () => {
    signedInAs(REP_ME)
    onBoard()
    const closes: Record<string, unknown>[] = []
    server.use(
      http.post(`*/api/v1/opportunities/${OPPORTUNITY.id}/close`, async ({ request }) => {
        closes.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({ ...OPPORTUNITY, stage: summary(STAGES[4]), version: 3 })
      }),
    )
    await renderApp('/opportunities/board')
    const move = await screen.findByRole('combobox', { name: 'Move Branch connectivity to' })
    await userEvent.selectOptions(move, 'close:lost')
    expect(screen.getByRole('form', { name: 'Close as lost' })).toBeInTheDocument()
    expect(closes).toEqual([])
    await userEvent.selectOptions(move, 'close:won')
    await waitFor(() => {
      expect(closes).toEqual([{ outcome: 'won', version: 2 }])
    })
  })

  it('FR-OPP-03 AC2 cards the user may not edit cannot be moved', async () => {
    signedInAs(REP_ME)
    onBoard([card({ can_edit: false, is_stale: true })])
    await renderApp('/opportunities/board')
    expect(await screen.findByRole('link', { name: 'Branch connectivity' })).toBeInTheDocument()
    expect(screen.getByText('Needs attention')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Drag/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: /^Move/ })).not.toBeInTheDocument()
  })

  it('FR-I18N-01 shows Bulgarian stage names', async () => {
    signedInAs({ ...REP_ME, locale: 'bg' })
    onBoard()
    await renderApp('/opportunities/board', 'bg')
    expect(await screen.findByRole('heading', { name: 'Табло на продажбите' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Квалификация' })).toBeInTheDocument()
    expect(screen.getByTestId(`totals-${STAGES[1].id}`)).toHaveTextContent('1 възможност')
  })
})

describe('FR-OPP-02 / FR-ADM-02 stage administration', () => {
  it('deactivates a stage and explains why a used stage cannot be deleted', async () => {
    signedInAs(ADMIN_ME)
    let patched: Record<string, unknown> = {}
    server.use(
      http.patch(`*/api/v1/pipelines/${PIPELINE.id}/stages/:stageId`, async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(PIPELINE)
      }),
      http.delete(`*/api/v1/pipelines/${PIPELINE.id}/stages/:stageId`, () =>
        problem(409, 'stage.in_use'),
      ),
    )
    await renderApp('/admin/stages')
    expect(await screen.findByDisplayValue('Solution & Proposal')).toBeInTheDocument()
    const [deactivate] = screen.getAllByRole('button', { name: 'Deactivate' })
    if (!deactivate) throw new Error('no stage rows')
    await userEvent.click(deactivate)
    await waitFor(() => {
      expect(patched).toEqual({ is_active: false })
    })
    const [remove] = screen.getAllByRole('button', { name: 'Delete' })
    if (!remove) throw new Error('no stage rows')
    await userEvent.click(remove)
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }))
    expect(
      await screen.findByText('This stage is in use. Deactivate it instead.'),
    ).toBeInTheDocument()
  })
})
