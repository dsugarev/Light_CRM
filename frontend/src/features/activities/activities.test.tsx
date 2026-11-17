import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { Schemas } from '@/api/client'
import {
  OPPORTUNITY,
  opportunityLists,
  page,
  REP_ME,
  signedInAs,
  STAGES,
  summary,
} from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const CALL: Schemas['ActivityOut'] = {
  id: '01930000-0000-7000-8000-0000000007a1',
  type: 'call',
  subject: 'Discovery call',
  body: 'Three sites, fibre preferred.',
  occurred_at: '2026-11-17T08:30:00Z',
  due_at: null,
  done_at: null,
  is_done: false,
  is_overdue: false,
  owner: { id: REP_ME.id, full_name: REP_ME.full_name },
  assignee: null,
  links: {
    lead: { id: 'lead-1', name: 'Fibre for 3 branches' },
    opportunity: { id: OPPORTUNITY.id, name: OPPORTUNITY.name },
    organization: null,
    contact: null,
  },
  created_at: '2026-11-17T08:30:00Z',
  updated_at: '2026-11-17T08:30:00Z',
  created_by: { id: REP_ME.id, full_name: REP_ME.full_name },
  archived_at: null,
  version: 1,
}

const TASK: Schemas['ActivityOut'] = {
  ...CALL,
  id: '01930000-0000-7000-8000-0000000007a2',
  type: 'task',
  subject: 'Send the offer',
  body: null,
  due_at: '2026-11-10T09:00:00Z',
  is_overdue: true,
  assignee: { id: REP_ME.id, full_name: REP_ME.full_name },
  version: 2,
}

function onOpportunityWithTimeline(items: Schemas['TimelineItem'][]) {
  server.use(
    http.get(`*/api/v1/opportunities/${OPPORTUNITY.id}`, () => HttpResponse.json(OPPORTUNITY)),
    http.get(`*/api/v1/opportunities/${OPPORTUNITY.id}/stage-history`, () => HttpResponse.json([])),
    http.get(`*/api/v1/opportunities/${OPPORTUNITY.id}/timeline`, () =>
      HttpResponse.json({ items, total: items.length, page: 1, page_size: 20 }),
    ),
    http.get('*/api/v1/users/lookup', () =>
      HttpResponse.json(
        page([{ id: REP_ME.id, full_name: REP_ME.full_name, email: REP_ME.email }]),
      ),
    ),
  )
}

beforeEach(() => {
  opportunityLists()
})

describe('FR-ACT-03 timeline', () => {
  it('merges activities with system events, including the source lead', async () => {
    signedInAs(REP_ME)
    onOpportunityWithTimeline([
      {
        id: 'e-1',
        kind: 'event',
        occurred_at: '2026-11-17T09:00:00Z',
        actor: { id: REP_ME.id, full_name: REP_ME.full_name },
        event: {
          type: 'stage_changed',
          entity_type: 'opportunity',
          entity_id: OPPORTUNITY.id,
          data: { from_stage: summary(STAGES[0]), to_stage: summary(STAGES[1]) },
        },
      },
      {
        id: CALL.id,
        kind: 'activity',
        occurred_at: CALL.occurred_at,
        actor: CALL.owner,
        activity: CALL,
      },
      {
        id: 'e-2',
        kind: 'event',
        occurred_at: '2026-11-17T08:00:00Z',
        actor: null,
        event: {
          type: 'status_changed',
          entity_type: 'lead',
          entity_id: 'lead-1',
          data: { from_status: 'contacted', to_status: 'qualified' },
        },
      },
    ])
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    const timeline = await screen.findByRole('list', { name: 'Timeline' })
    const [stage, call, status] = within(timeline).getAllByRole('listitem')
    if (!stage || !call || !status) throw new Error('expected three timeline entries')
    expect(stage).toHaveTextContent('Stage changed from Prospecting to Qualification')
    expect(call).toHaveTextContent('Discovery call')
    expect(call).toHaveTextContent('Three sites, fibre preferred.')
    expect(
      within(call).getByRole('link', { name: 'Lead: Fibre for 3 branches' }),
    ).toBeInTheDocument()
    expect(status).toHaveTextContent('Status changed from Contacted to Qualified')
    expect(within(status).getByRole('link', { name: 'Open' })).toHaveAttribute(
      'href',
      '/leads/lead-1',
    )
  })

  it('FR-ACT-01 logs a call against the record', async () => {
    signedInAs(REP_ME)
    onOpportunityWithTimeline([])
    let body: Record<string, unknown> = {}
    server.use(
      http.post('*/api/v1/activities', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(CALL, { status: 201 })
      }),
    )
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    expect(await screen.findByText('No activity yet.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Log activity' }))
    const form = screen.getByRole('form', { name: 'Log activity' })
    await userEvent.click(within(form).getByRole('button', { name: 'Log activity' }))
    expect(await within(form).findByText('Required.')).toBeInTheDocument()
    await userEvent.type(within(form).getByLabelText('Subject'), 'Discovery call')
    await userEvent.type(within(form).getByLabelText('Details'), 'Three sites')
    await userEvent.click(within(form).getByRole('button', { name: 'Log activity' }))
    await waitFor(() => {
      expect(body).toMatchObject({
        type: 'call',
        subject: 'Discovery call',
        body: 'Three sites',
        occurred_at: null,
        opportunity_id: OPPORTUNITY.id,
      })
    })
  })

  it('FR-ACT-02 a task needs a due date', async () => {
    signedInAs(REP_ME)
    onOpportunityWithTimeline([])
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Log activity' }))
    const form = screen.getByRole('form', { name: 'Log activity' })
    await userEvent.selectOptions(within(form).getByLabelText('Type'), 'task')
    await userEvent.type(within(form).getByLabelText('Subject'), 'Send the offer')
    await userEvent.click(within(form).getByRole('button', { name: 'Create task' }))
    expect(await within(form).findByText('A task needs a due date.')).toBeInTheDocument()
  })
})

describe('FR-ACT-03 timeline freshness', () => {
  it('reloads the timeline after a change to the record', async () => {
    signedInAs(REP_ME)
    onOpportunityWithTimeline([])
    let loads = 0
    server.use(
      http.get(`*/api/v1/opportunities/${OPPORTUNITY.id}/timeline`, () => {
        loads += 1
        return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 })
      }),
      http.post(`*/api/v1/opportunities/${OPPORTUNITY.id}/move`, () =>
        HttpResponse.json({ ...OPPORTUNITY, stage: summary(STAGES[2]), version: 3 }),
      ),
    )
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    await userEvent.selectOptions(
      await screen.findByRole('combobox', { name: 'Stage' }),
      STAGES[2].id,
    )
    const before = loads
    await userEvent.click(screen.getByRole('button', { name: 'Move' }))
    await waitFor(() => {
      expect(loads).toBeGreaterThan(before)
    })
  })
})

describe('FR-ACT-02 my tasks', () => {
  it('shows overdue tasks and marks them done', async () => {
    signedInAs(REP_ME)
    let body: Record<string, unknown> = {}
    server.use(
      http.get('*/api/v1/me/tasks', () => HttpResponse.json(page([TASK]))),
      http.post(`*/api/v1/activities/${TASK.id}/complete`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...TASK, is_done: true, version: 3 })
      }),
    )
    await renderApp('/tasks')
    const table = await screen.findByRole('table', { name: 'My tasks' })
    expect(within(table).getByText('Send the offer')).toBeInTheDocument()
    expect(within(table).getByText('Overdue')).toBeInTheDocument()
    expect(
      within(table).getByRole('link', { name: `Opportunity: ${OPPORTUNITY.name}` }),
    ).toBeInTheDocument()
    await userEvent.click(within(table).getByRole('checkbox', { name: 'Done: Send the offer' }))
    await waitFor(() => {
      expect(body).toEqual({ version: 2 })
    })
  })
})
