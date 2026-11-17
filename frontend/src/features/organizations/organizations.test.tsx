import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ADMIN_ME, CONTACT, ORG, page, referenceLists, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

beforeEach(() => {
  referenceLists()
})

describe('FR-PARTY-04 organization list', () => {
  it('shows organizations with translated industry and keeps sort and filters in the URL', async () => {
    signedInAs({ ...REP_ME, locale: 'bg' })
    const requests: string[] = []
    server.use(
      http.get('*/api/v1/organizations', ({ request }) => {
        requests.push(new URL(request.url).search)
        return HttpResponse.json(page([ORG]))
      }),
    )
    const { router } = await renderApp('/organizations', 'bg')
    const table = await screen.findByRole('table', { name: 'Организации' })
    expect(within(table).getByRole('link', { name: 'Акме ЕООД' })).toBeInTheDocument()
    expect(within(table).getByText('Телекомуникации')).toBeInTheDocument()

    await userEvent.click(within(table).getByRole('button', { name: /Име/ }))
    await waitFor(() => {
      expect(router.state.location.search).toBe('?sort=-name')
    })
    expect(within(table).getByRole('columnheader', { name: /Име/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    )
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Отговорник' }), 'me')
    await waitFor(() => {
      expect(requests.at(-1)).toContain('owner_id=me')
    })
    expect(router.state.location.search).toContain('owner_id=me')
  })

  it('searches after typing pauses', async () => {
    signedInAs(REP_ME)
    const requests: string[] = []
    server.use(
      http.get('*/api/v1/organizations', ({ request }) => {
        requests.push(new URL(request.url).searchParams.get('q') ?? '')
        return HttpResponse.json(page([]))
      }),
    )
    await renderApp('/organizations')
    await userEvent.type(await screen.findByRole('searchbox', { name: /Search by name/ }), 'софия')
    await waitFor(() => {
      expect(requests.at(-1)).toBe('софия')
    })
    expect(await screen.findByText('Nothing to show.')).toBeInTheDocument()
  })
})

describe('FR-PARTY-01 create organization', () => {
  it('AC1 warns about possible duplicates before saving, with a link', async () => {
    signedInAs(REP_ME)
    server.use(
      http.get('*/api/v1/organizations/duplicate-check', () =>
        HttpResponse.json({
          matches: [
            {
              id: ORG.id,
              name: ORG.name,
              registration_number: null,
              email: null,
              city: 'София',
              archived: false,
              reason: 'name',
            },
          ],
        }),
      ),
    )
    await renderApp('/organizations/new')
    await userEvent.type(await screen.findByLabelText('Name'), 'ACME eood')
    const warning = await screen.findByTestId('duplicate-matches')
    expect(within(warning).getByRole('link', { name: 'Акме ЕООД' })).toHaveAttribute(
      'href',
      `/organizations/${ORG.id}`,
    )
    expect(warning).toHaveTextContent('same name')
  })

  it('AC1 offers "Create anyway" after a 409 and resends with confirm_duplicate', async () => {
    signedInAs(REP_ME)
    const bodies: Record<string, unknown>[] = []
    server.use(
      http.get('*/api/v1/organizations/duplicate-check', () => HttpResponse.json({ matches: [] })),
      http.post('*/api/v1/organizations', async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        bodies.push(body)
        if (!body['confirm_duplicate']) {
          return problem(409, 'conflict.duplicate', {
            matches: [
              {
                id: ORG.id,
                name: ORG.name,
                registration_number: '123456786',
                email: null,
                city: null,
                archived: true,
                reason: 'registration_number',
              },
            ],
          })
        }
        return HttpResponse.json(
          {
            ...ORG,
            id: 'new-id',
            warnings: [
              { field: 'registration_number', code: 'organization.registration_checksum' },
            ],
          },
          { status: 201 },
        )
      }),
      http.get('*/api/v1/organizations/new-id', () =>
        HttpResponse.json({
          ...ORG,
          id: 'new-id',
          counts: {
            contacts: 0,
            open_leads: 0,
            open_opportunities: 0,
            open_pipeline_value: '0.00',
            currency: 'EUR',
          },
        }),
      ),
      http.get('*/api/v1/organizations/new-id/contacts', () => HttpResponse.json(page([]))),
    )
    const { router } = await renderApp('/organizations/new')
    await userEvent.type(await screen.findByLabelText('Name'), 'Acme')
    await userEvent.type(screen.getByLabelText('EIK / UIC'), '123456786')
    await userEvent.click(screen.getByRole('button', { name: 'Create organization' }))
    const conflict = await screen.findByTestId('duplicate-matches')
    expect(conflict).toHaveTextContent('same EIK')
    expect(conflict).toHaveTextContent('archived')
    await userEvent.click(within(conflict).getByRole('button', { name: 'Create anyway' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/organizations/new-id')
    })
    expect(bodies[0]).toMatchObject({
      name: 'Acme',
      registration_number: '123456786',
      country: 'BG',
      confirm_duplicate: false,
    })
    expect(bodies[1]).toMatchObject({ confirm_duplicate: true })
    expect(await screen.findByText('Organization created.')).toBeInTheDocument()
    expect(
      await screen.findAllByText('The EIK check digit does not match. Please verify the number.'),
    ).not.toHaveLength(0)
  })

  it('validates EIK, VAT, website and country on the client', async () => {
    signedInAs(REP_ME)
    await renderApp('/organizations/new')
    await userEvent.type(await screen.findByLabelText('EIK / UIC'), '12345')
    await userEvent.type(screen.getByLabelText('VAT number'), 'DE1')
    await userEvent.type(screen.getByLabelText('Website'), 'acme.example')
    await userEvent.clear(screen.getByLabelText('Country'))
    await userEvent.click(screen.getByRole('button', { name: 'Create organization' }))
    expect(await screen.findByText('9 or 13 digits.')).toBeInTheDocument()
    expect(screen.getByText('BG followed by 9 or 10 digits.')).toBeInTheDocument()
    expect(
      screen.getByText('Enter a web address starting with http:// or https://'),
    ).toBeInTheDocument()
    expect(screen.getByText('Two letters, e.g. BG.')).toBeInTheDocument()
    expect(screen.getByText('Required.')).toBeInTheDocument()
  })

  it('shows the owner picker only to users who may reassign', async () => {
    signedInAs(ADMIN_ME)
    server.use(
      http.get('*/api/v1/users/lookup', () =>
        HttpResponse.json(
          page([{ id: ADMIN_ME.id, full_name: 'Ada Admin', email: ADMIN_ME.email }]),
        ),
      ),
    )
    await renderApp('/organizations/new')
    expect(await screen.findByLabelText('Owner')).toBeInTheDocument()
  })
})

describe('FR-PARTY-03 organization 360', () => {
  const detail = {
    ...ORG,
    counts: {
      contacts: 1,
      open_leads: 0,
      open_opportunities: 0,
      open_pipeline_value: '0.00',
      currency: 'EUR' as const,
    },
  }

  it('shows details, counts, contacts and empty later-phase sections', async () => {
    signedInAs(REP_ME)
    server.use(
      http.get(`*/api/v1/organizations/${ORG.id}`, () => HttpResponse.json(detail)),
      http.get(`*/api/v1/organizations/${ORG.id}/contacts`, () =>
        HttpResponse.json(page([CONTACT])),
      ),
    )
    await renderApp(`/organizations/${ORG.id}`)
    expect(await screen.findByRole('heading', { name: 'Акме ЕООД' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Мария Иванова' })).toBeInTheDocument()
    expect(screen.getByText('€0.00')).toBeInTheDocument()
    expect(screen.getByText('No leads yet.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add contact' })).toHaveAttribute(
      'href',
      `/contacts/new?organization_id=${ORG.id}`,
    )
  })

  it('FR-AUTH-05 hides edit and archive from a rep who does not own it', async () => {
    signedInAs({ ...REP_ME, id: 'someone-else' })
    server.use(
      http.get(`*/api/v1/organizations/${ORG.id}`, () => HttpResponse.json(detail)),
      http.get(`*/api/v1/organizations/${ORG.id}/contacts`, () => HttpResponse.json(page([]))),
    )
    await renderApp(`/organizations/${ORG.id}`)
    expect(await screen.findByRole('heading', { name: 'Акме ЕООД' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
  })

  it('archives after confirmation', async () => {
    signedInAs(REP_ME)
    let archived = false
    server.use(
      http.get(`*/api/v1/organizations/${ORG.id}`, () =>
        HttpResponse.json(archived ? { ...detail, archived_at: '2026-11-17T10:00:00Z' } : detail),
      ),
      http.get(`*/api/v1/organizations/${ORG.id}/contacts`, () => HttpResponse.json(page([]))),
      http.delete(`*/api/v1/organizations/${ORG.id}`, () => {
        archived = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await renderApp(`/organizations/${ORG.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    await userEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Confirm' }),
    )
    expect(await screen.findByText(/Archived on/)).toBeInTheDocument()
    expect(screen.getByText('Organization archived.')).toBeInTheDocument()
  })
})
