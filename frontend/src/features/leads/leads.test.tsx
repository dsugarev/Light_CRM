import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import {
  ADMIN_ME,
  LEAD,
  leadLists,
  OPPORTUNITY,
  opportunityLists,
  ORG,
  page,
  REP_ME,
  signedInAs,
  STAGES,
  summary,
} from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

beforeEach(() => {
  leadLists()
})

function onLead(lead = LEAD) {
  server.use(http.get(`*/api/v1/leads/${lead.id}`, () => HttpResponse.json(lead)))
}

describe('FR-LEAD-05 lead list', () => {
  it('shows status, score and value, with filters in the URL', async () => {
    signedInAs(REP_ME)
    const requests: string[] = []
    server.use(
      http.get('*/api/v1/leads', ({ request }) => {
        requests.push(new URL(request.url).search)
        return HttpResponse.json(page([LEAD]))
      }),
    )
    const { router } = await renderApp('/leads')
    const table = await screen.findByRole('table', { name: 'Leads' })
    expect(within(table).getByRole('link', { name: 'Fibre for 3 branches' })).toBeInTheDocument()
    expect(within(table).getByText('Contacted')).toBeInTheDocument()
    expect(within(table).getByText('63')).toBeInTheDocument()
    expect(within(table).getByText('€48,000.00')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'qualified')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Fits target profile' }))
    await waitFor(() => {
      expect(router.state.location.search).toContain('status=qualified')
    })
    expect(router.state.location.search).toContain('fits_target_profile=true')
    await waitFor(() => {
      expect(requests.at(-1)).toContain('fits_target_profile=true')
    })
  })
})

describe('FR-LEAD-01 capture', () => {
  it('saves with only a title and company name', async () => {
    signedInAs(REP_ME)
    let body: Record<string, unknown> = {}
    server.use(
      http.post('*/api/v1/leads', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...LEAD, status: 'new' }, { status: 201 })
      }),
    )
    onLead({ ...LEAD, status: 'new' })
    const { router } = await renderApp('/leads/new')
    await userEvent.type(await screen.findByLabelText('Title'), 'Fibre for 3 branches')
    await userEvent.type(screen.getByLabelText('Company'), 'Акме ЕООД')
    await userEvent.type(screen.getByLabelText('Estimated value (EUR)'), '48000,50')
    await userEvent.click(screen.getByRole('button', { name: 'Create lead' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/leads/${LEAD.id}`)
    })
    expect(body).toMatchObject({
      title: 'Fibre for 3 branches',
      company_name: 'Акме ЕООД',
      estimated_value: '48000.50',
      organization_id: null,
    })
  })

  it('validates the amount on the client', async () => {
    signedInAs(REP_ME)
    await renderApp('/leads/new')
    await userEvent.type(await screen.findByLabelText('Estimated value (EUR)'), 'lots')
    await userEvent.click(screen.getByRole('button', { name: 'Create lead' }))
    expect(await screen.findByText('Enter an amount, e.g. 48000 or 48000.50.')).toBeInTheDocument()
  })
})

describe('FR-LEAD-02, 03 lead detail', () => {
  it('FR-LEAD-03 shows BANT, recomputes the score live and saves with the version', async () => {
    signedInAs(REP_ME)
    onLead()
    let body: Record<string, unknown> = {}
    server.use(
      http.patch(`*/api/v1/leads/${LEAD.id}`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...LEAD, version: 4 })
      }),
    )
    await renderApp(`/leads/${LEAD.id}`)
    expect(await screen.findByTestId('bant-score')).toHaveTextContent('63')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Timeline' }), 'yes')
    expect(screen.getByTestId('bant-score')).toHaveTextContent('88')
    await userEvent.click(screen.getByRole('button', { name: 'Save qualification' }))
    await waitFor(() => {
      expect(body).toMatchObject({
        version: 3,
        qualification: { timeline: { status: 'yes' }, fits_target_profile: true },
      })
    })
  })

  it('FR-LEAD-03 AC1 disables Qualify while a BANT item is unknown', async () => {
    signedInAs(REP_ME)
    onLead()
    await renderApp(`/leads/${LEAD.id}`)
    expect(await screen.findByRole('button', { name: 'Qualify' })).toBeDisabled()
  })

  it('FR-LEAD-02 AC1 disqualifying needs a reason', async () => {
    signedInAs(REP_ME)
    onLead()
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`*/api/v1/leads/${LEAD.id}/disqualify`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...LEAD,
          status: 'disqualified',
          version: 4,
          disqualification: {
            reason: { id: 'r-1', code: 'no_budget', name_en: 'No budget', name_bg: 'Няма бюджет' },
            note: 'Frozen',
            disqualified_at: '2026-11-17T10:00:00Z',
          },
        })
      }),
    )
    await renderApp(`/leads/${LEAD.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Disqualify' }))
    const form = screen.getByRole('form', { name: 'Disqualify lead' })
    await userEvent.click(within(form).getByRole('button', { name: 'Disqualify' }))
    expect(within(form).getByText('Required.')).toBeInTheDocument()
    await userEvent.selectOptions(within(form).getByLabelText('Reason'), 'r-1')
    await userEvent.type(within(form).getByLabelText('Note'), 'Frozen')
    await userEvent.click(within(form).getByRole('button', { name: 'Disqualify' }))
    expect(
      await screen.findByText(/Disqualified on 17 Nov 2026: No budget — Frozen/),
    ).toBeInTheDocument()
    expect(body).toEqual({ reason_id: 'r-1', note: 'Frozen', version: 3 })
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('FR-LEAD-02 AC2 shows Reopen to managers only', async () => {
    const disqualified = {
      ...LEAD,
      status: 'disqualified' as const,
      disqualification: { reason: null, note: null, disqualified_at: '2026-11-17T10:00:00Z' },
    }
    signedInAs(REP_ME)
    onLead(disqualified)
    const { unmount } = await renderApp(`/leads/${LEAD.id}`)
    expect(await screen.findByText(/Disqualified on/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reopen' })).not.toBeInTheDocument()
    unmount()
    signedInAs(ADMIN_ME)
    await renderApp(`/leads/${LEAD.id}`)
    expect(await screen.findByRole('button', { name: 'Reopen' })).toBeInTheDocument()
  })

  it('shows the latest version after a conflict', async () => {
    signedInAs(REP_ME)
    onLead({ ...LEAD, status: 'new' })
    server.use(
      http.post(`*/api/v1/leads/${LEAD.id}/mark-contacted`, () =>
        problem(409, 'conflict.version_mismatch', {
          current: { ...LEAD, title: 'Changed by someone', version: 9 },
        }),
      ),
    )
    await renderApp(`/leads/${LEAD.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Mark as contacted' }))
    expect(await screen.findByRole('heading', { name: 'Changed by someone' })).toBeInTheDocument()
    expect(screen.getByText(/Someone else changed this lead/)).toBeInTheDocument()
  })

  it("FR-LEAD-06 lets a rep take over another rep's lead", async () => {
    signedInAs({ ...REP_ME, id: 'other-rep' })
    onLead()
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`*/api/v1/leads/${LEAD.id}/assign`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...LEAD,
          owner: { id: 'other-rep', full_name: 'Boris Rep' },
          version: 4,
        })
      }),
    )
    await renderApp(`/leads/${LEAD.id}`)
    expect(screen.queryByRole('button', { name: 'Mark as contacted' })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Take over' }))
    await waitFor(() => {
      expect(body).toEqual({ owner_id: 'other-rep', version: 3 })
    })
  })
})

describe('FR-ADM-02 lead lists administration', () => {
  it('switches between the three lists', async () => {
    signedInAs(ADMIN_ME)
    server.use(http.get('*/api/v1/reference/industries', () => HttpResponse.json([])))
    await renderApp('/admin/reference/industries')
    await userEvent.click(await screen.findByRole('link', { name: 'Disqualification reasons' }))
    expect(await screen.findByText('No budget')).toBeInTheDocument()
  })
})

describe('FR-LEAD-04 conversion', () => {
  const qualified = { ...LEAD, status: 'qualified' as const }
  const preview = {
    organization: {
      linked: null,
      matches: [
        {
          id: 'org-acme',
          name: 'ACME EOOD',
          registration_number: null,
          email: null,
          city: 'София',
          archived: false,
          reason: 'name' as const,
        },
      ],
      suggested: { name: 'Акме ЕООД' },
    },
    contact: {
      linked: null,
      matches: [],
      suggested: {
        first_name: 'Мария',
        last_name: 'Иванова',
        email: 'maria@example.test',
        phone: null,
      },
    },
    opportunity: { name: LEAD.title, amount: '48000.00', stage: summary(STAGES[0]) },
  }

  function onConversion() {
    opportunityLists()
    server.use(
      http.get(`*/api/v1/leads/${LEAD.id}`, () => HttpResponse.json(qualified)),
      http.get(`*/api/v1/leads/${LEAD.id}/conversion-preview`, () => HttpResponse.json(preview)),
    )
  }

  it('offers Convert on a qualified lead', async () => {
    signedInAs(REP_ME)
    onLead(qualified)
    await renderApp(`/leads/${LEAD.id}`)
    expect(await screen.findByRole('link', { name: 'Convert' })).toHaveAttribute(
      'href',
      `/leads/${LEAD.id}/convert`,
    )
  })

  it('shows the opportunity a converted lead became', async () => {
    signedInAs(REP_ME)
    onLead({
      ...LEAD,
      status: 'converted',
      converted_opportunity: { id: OPPORTUNITY.id, name: OPPORTUNITY.name },
    })
    await renderApp(`/leads/${LEAD.id}`)
    expect(await screen.findByRole('link', { name: OPPORTUNITY.name })).toHaveAttribute(
      'href',
      `/opportunities/${OPPORTUNITY.id}`,
    )
    expect(screen.queryByRole('link', { name: 'Convert' })).not.toBeInTheDocument()
  })

  it('suggests the matching organization and converts in one request', async () => {
    signedInAs(REP_ME)
    onConversion()
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`*/api/v1/leads/${LEAD.id}/convert`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(
          { lead: qualified, organization: ORG, contact: null, opportunity: OPPORTUNITY },
          { status: 201 },
        )
      }),
    )
    onOpportunityPage()
    const { router } = await renderApp(`/leads/${LEAD.id}/convert`)
    const organization = await screen.findByRole('group', { name: 'Organization' })
    expect(
      within(organization).getByRole('radio', { name: /ACME EOOD, София — same name/ }),
    ).toBeChecked()
    const contact = screen.getByRole('group', { name: 'Contact' })
    expect(within(contact).getByRole('radio', { name: 'Create a new contact' })).toBeChecked()
    expect(screen.getByLabelText('First name')).toHaveValue('Мария')
    expect(screen.getByLabelText('Opportunity name')).toHaveValue(LEAD.title)
    await userEvent.type(screen.getByLabelText('Expected close date'), '2027-02-28')
    await userEvent.click(screen.getByRole('button', { name: 'Convert' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/opportunities/${OPPORTUNITY.id}`)
    })
    expect(body).toMatchObject({
      version: 3,
      organization: { existing_id: 'org-acme' },
      contact: { new: { first_name: 'Мария', last_name: 'Иванова', email: 'maria@example.test' } },
      opportunity: { name: LEAD.title, amount: '48000.00', expected_close_date: '2027-02-28' },
    })
  })

  it('asks before creating a duplicate organization', async () => {
    signedInAs(REP_ME)
    onConversion()
    const bodies: Record<string, unknown>[] = []
    server.use(
      http.post(`*/api/v1/leads/${LEAD.id}/convert`, async ({ request }) => {
        const body = (await request.json()) as {
          organization: { new?: { confirm_duplicate: boolean } }
        }
        bodies.push(body)
        return body.organization.new?.confirm_duplicate
          ? HttpResponse.json(
              { lead: qualified, organization: ORG, contact: null, opportunity: OPPORTUNITY },
              { status: 201 },
            )
          : problem(409, 'conflict.duplicate', { matches: [preview.organization.matches[0]] })
      }),
    )
    onOpportunityPage()
    await renderApp(`/leads/${LEAD.id}/convert`)
    await userEvent.click(await screen.findByRole('radio', { name: 'Create a new organization' }))
    await userEvent.click(screen.getByRole('button', { name: 'Convert' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Records with the same details already exist')
    await userEvent.click(within(alert).getByRole('checkbox', { name: 'Create anyway' }))
    await userEvent.click(screen.getByRole('button', { name: 'Convert' }))
    await waitFor(() => {
      expect(bodies).toHaveLength(2)
    })
    expect(bodies[1]).toMatchObject({
      organization: { new: { name: 'Акме ЕООД', confirm_duplicate: true } },
    })
  })
})

function onOpportunityPage() {
  server.use(
    http.get(`*/api/v1/opportunities/${OPPORTUNITY.id}`, () => HttpResponse.json(OPPORTUNITY)),
    http.get(`*/api/v1/opportunities/${OPPORTUNITY.id}/stage-history`, () => HttpResponse.json([])),
  )
}
