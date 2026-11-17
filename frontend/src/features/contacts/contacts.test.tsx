import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import {
  ADMIN_ME,
  CONTACT,
  ORG,
  page,
  referenceLists,
  REP_ME,
  signedInAs,
  TELECOM,
} from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

beforeEach(() => {
  referenceLists()
})

describe('FR-PARTY-02 contacts', () => {
  it('lists contacts with their organization', async () => {
    signedInAs(REP_ME)
    server.use(http.get('*/api/v1/contacts', () => HttpResponse.json(page([CONTACT]))))
    await renderApp('/contacts')
    const table = await screen.findByRole('table', { name: 'Contacts' })
    expect(within(table).getByRole('link', { name: 'Мария Иванова' })).toBeInTheDocument()
    expect(within(table).getByRole('link', { name: 'Акме ЕООД' })).toBeInTheDocument()
  })

  it('creates a contact for the organization it was started from', async () => {
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
      http.post('*/api/v1/contacts', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(CONTACT, { status: 201 })
      }),
      http.get(`*/api/v1/contacts/${CONTACT.id}`, () => HttpResponse.json(CONTACT)),
    )
    const { router } = await renderApp(`/contacts/new?organization_id=${ORG.id}`)
    expect(await screen.findByText('Акме ЕООД')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('First name'), 'Мария')
    await userEvent.type(screen.getByLabelText('Last name'), 'Иванова')
    await userEvent.type(screen.getByLabelText('Email'), 'maria@example.test')
    await userEvent.click(screen.getByRole('button', { name: 'Create contact' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/contacts/${CONTACT.id}`)
    })
    expect(body).toMatchObject({
      first_name: 'Мария',
      last_name: 'Иванова',
      email: 'maria@example.test',
      organization_id: ORG.id,
      confirm_duplicate: false,
    })
  })

  it('picks an organization by searching', async () => {
    signedInAs(REP_ME)
    server.use(http.get('*/api/v1/organizations', () => HttpResponse.json(page([ORG]))))
    await renderApp('/contacts/new')
    await userEvent.type(
      await screen.findByRole('searchbox', { name: /Search by name, EIK/ }),
      'акме',
    )
    await userEvent.click(await screen.findByRole('button', { name: /Акме ЕООД/ }))
    expect(screen.getByRole('button', { name: 'No organization' })).toBeInTheDocument()
  })

  it('shows email duplicates after a 409', async () => {
    signedInAs(REP_ME)
    server.use(
      http.post('*/api/v1/contacts', () =>
        problem(409, 'conflict.duplicate', {
          matches: [
            {
              id: CONTACT.id,
              name: 'Мария Иванова',
              registration_number: null,
              email: 'maria@example.test',
              city: null,
              archived: false,
              reason: 'email',
            },
          ],
        }),
      ),
    )
    await renderApp('/contacts/new')
    await userEvent.type(await screen.findByLabelText('First name'), 'M')
    await userEvent.type(screen.getByLabelText('Last name'), 'I')
    await userEvent.type(screen.getByLabelText('Email'), 'maria@example.test')
    await userEvent.click(screen.getByRole('button', { name: 'Create contact' }))
    const matches = await screen.findByTestId('duplicate-matches')
    expect(matches).toHaveTextContent('same email')
    expect(within(matches).getByRole('button', { name: 'Create anyway' })).toBeInTheDocument()
  })

  it('shows a contact with links and the ownership note', async () => {
    signedInAs(REP_ME)
    server.use(http.get(`*/api/v1/contacts/${CONTACT.id}`, () => HttpResponse.json(CONTACT)))
    await renderApp(`/contacts/${CONTACT.id}`)
    expect(await screen.findByRole('heading', { name: 'Мария Иванова' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'maria@example.test' })).toHaveAttribute(
      'href',
      'mailto:maria@example.test',
    )
    expect(screen.getByText('Owner: Boris Rep (follows the organization)')).toBeInTheDocument()
  })
})

describe('FR-ADM-02 reference list administration', () => {
  it('adds a value and explains why a used value cannot be deleted', async () => {
    signedInAs(ADMIN_ME)
    let posted: unknown
    server.use(
      http.get('*/api/v1/reference/industries', () => HttpResponse.json([TELECOM])),
      http.post('*/api/v1/reference/industries', async ({ request }) => {
        posted = await request.json()
        return HttpResponse.json({ ...TELECOM, id: 'n', code: 'agriculture' }, { status: 201 })
      }),
      http.delete('*/api/v1/reference/industries/:id', () => problem(409, 'reference.in_use')),
    )
    await renderApp('/admin/reference/industries')
    expect(await screen.findByText('Телекомуникации')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Code'), 'agriculture')
    await userEvent.type(screen.getByLabelText('Name (English)'), 'Agriculture')
    await userEvent.type(screen.getByLabelText('Name (Bulgarian)'), 'Земеделие')
    await userEvent.click(screen.getByRole('button', { name: 'Add value' }))
    await waitFor(() => {
      expect(posted).toEqual({
        code: 'agriculture',
        name_en: 'Agriculture',
        name_bg: 'Земеделие',
        is_active: true,
      })
    })
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await userEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Confirm' }),
    )
    expect(
      await screen.findByText('This value is in use. Deactivate it instead.'),
    ).toBeInTheDocument()
  })
})

describe('FR-PARTY-04 global search', () => {
  it('searches from the header and shows grouped results', async () => {
    signedInAs(REP_ME)
    server.use(
      http.get('*/api/v1/search', ({ request }) => {
        expect(new URL(request.url).searchParams.get('q')).toBe('sofia')
        return HttpResponse.json({
          items: [
            { type: 'organization', id: ORG.id, label: ORG.name, detail: 'София' },
            { type: 'contact', id: CONTACT.id, label: CONTACT.full_name, detail: ORG.name },
          ],
        })
      }),
    )
    const { router } = await renderApp('/')
    await userEvent.type(
      await screen.findByRole('searchbox', { name: 'Search organizations and contacts' }),
      'sofia{Enter}',
    )
    expect(await screen.findByRole('heading', { name: 'Results for “sofia”' })).toBeInTheDocument()
    expect(router.state.location.search).toBe('?q=sofia')
    expect(screen.getByRole('link', { name: 'Акме ЕООД' })).toHaveAttribute(
      'href',
      `/organizations/${ORG.id}`,
    )
    expect(screen.getByRole('link', { name: 'Мария Иванова' })).toHaveAttribute(
      'href',
      `/contacts/${CONTACT.id}`,
    )
  })
})
