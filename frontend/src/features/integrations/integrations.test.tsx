import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { Schemas } from '@/api/client'
import { ADMIN_ME, ORG, page, referenceLists, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

const ERP: Schemas['SystemSummary'] = {
  id: '01930000-0000-7000-8000-0000000006a1',
  code: 'erp',
  name_en: 'ERP',
  name_bg: 'ERP система',
}

const ERP_ITEM: Schemas['ReferenceItem'] = { ...ERP, position: 2, is_active: true }

const CLIENT: Schemas['IntegrationClientOut'] = {
  id: '01930000-0000-7000-8000-0000000006c1',
  name: 'ERP (read-only)',
  system: ERP,
  scopes: ['organizations:read', 'reference:read'],
  is_active: false,
  default_owner: null,
  ip_allowlist: [],
  rate_limit_per_minute: 300,
  technical_contact: null,
  active_keys: 0,
  last_used_at: null,
  usage: { requests_24h: 12, errors_24h: 1 },
  webhooks: { subscriptions: 0, failing_deliveries: 0, suspended_subscriptions: 0 },
  created_at: '2026-11-17T09:00:00Z',
  updated_at: '2026-11-17T09:00:00Z',
}

const KEY: Schemas['ApiKeyOut'] = {
  id: '01930000-0000-7000-8000-0000000006k1',
  label: 'Production',
  prefix: 'crm_prod_0123456789abcdef',
  expires_at: '2027-11-17T09:00:00Z',
  last_used_at: null,
  last_used_ip: null,
  revoked_at: null,
  created_at: '2026-11-17T09:00:00Z',
  created_by: { id: ADMIN_ME.id, full_name: ADMIN_ME.full_name },
}

function onClient(
  client: Schemas['IntegrationClientOut'],
  keys: Schemas['ApiKeyOut'][] = [],
  subscriptions: Schemas['WebhookSubscriptionOut'][] = [],
) {
  server.use(
    http.get(`*/api/v1/integration-clients/${client.id}`, () => HttpResponse.json(client)),
    http.get(`*/api/v1/integration-clients/${client.id}/api-keys`, () => HttpResponse.json(keys)),
    http.get(`*/api/v1/integration-clients/${client.id}/webhook-subscriptions`, () =>
      HttpResponse.json(subscriptions),
    ),
    http.get('*/api/v1/users/lookup', () => HttpResponse.json(page([]))),
  )
}

describe('FR-INT-01 integration clients', () => {
  it('lists clients and creates a new one inactive', async () => {
    signedInAs(ADMIN_ME)
    let body: Record<string, unknown> = {}
    server.use(
      http.get('*/api/v1/integration-clients', () => HttpResponse.json([CLIENT])),
      http.get('*/api/v1/reference/external-systems', () => HttpResponse.json([ERP_ITEM])),
      http.post('*/api/v1/integration-clients', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(CLIENT, { status: 201 })
      }),
    )
    onClient(CLIENT)
    const { router } = await renderApp('/admin/integrations')
    const table = await screen.findByRole('table', { name: 'Integrations' })
    expect(within(table).getByRole('link', { name: 'ERP (read-only)' })).toBeInTheDocument()
    expect(within(table).getByText('Inactive')).toBeInTheDocument()
    expect(within(table).getByText('12 requests, 1 errors')).toBeInTheDocument()

    const form = screen.getByRole('form', { name: 'New integration client' })
    await userEvent.type(within(form).getByLabelText('Name'), 'ERP sync')
    await userEvent.selectOptions(await within(form).findByLabelText('System'), 'erp')
    await userEvent.click(within(form).getByRole('checkbox', { name: /organizations:read/ }))
    await userEvent.click(within(form).getByRole('button', { name: 'Create client' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/admin/integrations/${CLIENT.id}`)
    })
    expect(body).toMatchObject({
      name: 'ERP sync',
      system: 'erp',
      scopes: ['organizations:read'],
      is_active: false,
    })
  })

  it('keeps non-Admins out and hides the navigation link', async () => {
    signedInAs(REP_ME)
    const { router } = await renderApp('/admin/integrations')
    expect(await screen.findByRole('heading', { name: 'Welcome, Boris Rep' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    expect(screen.queryByRole('link', { name: 'Integrations' })).not.toBeInTheDocument()
  })

  it('shows the navigation link to Admins', async () => {
    signedInAs(ADMIN_ME)
    await renderApp('/')
    expect(await screen.findByRole('link', { name: 'Integrations' })).toBeInTheDocument()
  })
})

describe('FR-INT-01 client settings', () => {
  it('saves settings with the allowlist split into lines', async () => {
    signedInAs(ADMIN_ME)
    onClient(CLIENT)
    let body: Record<string, unknown> = {}
    server.use(
      http.patch(`*/api/v1/integration-clients/${CLIENT.id}`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(CLIENT)
      }),
    )
    await renderApp(`/admin/integrations/${CLIENT.id}`)
    const form = await screen.findByRole('form', { name: 'Settings' })
    const allowlist = within(form).getByLabelText('Allowed addresses')
    await userEvent.type(allowlist, '10.1.2.0/24{Enter}  192.0.2.7/32  ')
    await userEvent.clear(within(form).getByLabelText('Requests per minute'))
    await userEvent.type(within(form).getByLabelText('Requests per minute'), '120')
    await userEvent.click(within(form).getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      expect(body).toMatchObject({
        ip_allowlist: ['10.1.2.0/24', '192.0.2.7/32'],
        rate_limit_per_minute: 120,
        default_owner_id: null,
      })
    })
  })

  it('shows field errors from the server', async () => {
    signedInAs(ADMIN_ME)
    onClient(CLIENT)
    server.use(
      http.patch(`*/api/v1/integration-clients/${CLIENT.id}`, () =>
        problem(422, 'validation.failed', {
          errors: [{ field: 'ip_allowlist.0', code: 'validation.invalid' }],
        }),
      ),
    )
    await renderApp(`/admin/integrations/${CLIENT.id}`)
    const form = await screen.findByRole('form', { name: 'Settings' })
    await userEvent.type(within(form).getByLabelText('Allowed addresses'), 'nope')
    await userEvent.click(within(form).getByRole('button', { name: 'Save' }))
    expect(await within(form).findByLabelText('Allowed addresses')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
  })

  it('activates an inactive client', async () => {
    signedInAs(ADMIN_ME)
    onClient(CLIENT)
    let activated = false
    server.use(
      http.post(`*/api/v1/integration-clients/${CLIENT.id}/activate`, () => {
        activated = true
        return HttpResponse.json({ ...CLIENT, is_active: true })
      }),
    )
    await renderApp(`/admin/integrations/${CLIENT.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Activate' }))
    await waitFor(() => {
      expect(activated).toBe(true)
    })
  })
})

describe('FR-INT-02 API keys', () => {
  it('AC1 shows a new key once, then only its prefix', async () => {
    signedInAs(ADMIN_ME)
    onClient(CLIENT, [KEY])
    const secret = 'crm_prod_fedcba9876543210_' + 'a'.repeat(43)
    server.use(
      http.post(`*/api/v1/integration-clients/${CLIENT.id}/api-keys`, () =>
        HttpResponse.json(
          { ...KEY, id: 'k2', label: 'Rotation', prefix: 'crm_prod_fedcba9876543210', key: secret },
          { status: 201 },
        ),
      ),
    )
    await renderApp(`/admin/integrations/${CLIENT.id}`)
    const table = await screen.findByRole('table', { name: 'API keys' })
    expect(within(table).getByText(KEY.prefix)).toBeInTheDocument()
    expect(screen.queryByText('Copy the key now')).not.toBeInTheDocument()

    const form = screen.getByRole('form', { name: 'Create key' })
    await userEvent.type(within(form).getByLabelText('Label'), 'Rotation')
    await userEvent.click(within(form).getByRole('button', { name: 'Create key' }))
    expect(await screen.findByText('Copy the key now')).toBeInTheDocument()
    expect(screen.getByDisplayValue(secret)).toBeInTheDocument()
  })

  it('AC3 revokes a key after confirmation', async () => {
    signedInAs(ADMIN_ME)
    onClient(CLIENT, [KEY])
    let revoked = ''
    server.use(
      http.delete(`*/api/v1/integration-clients/${CLIENT.id}/api-keys/:keyId`, ({ params }) => {
        revoked = String(params['keyId'])
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await renderApp(`/admin/integrations/${CLIENT.id}`)
    const table = await screen.findByRole('table', { name: 'API keys' })
    await userEvent.click(within(table).getByRole('button', { name: 'Revoke' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }))
    await waitFor(() => {
      expect(revoked).toBe(KEY.id)
    })
  })

  it('explains the two-key limit', async () => {
    signedInAs(ADMIN_ME)
    onClient(CLIENT, [KEY])
    server.use(
      http.post(`*/api/v1/integration-clients/${CLIENT.id}/api-keys`, () =>
        problem(409, 'api_key.limit'),
      ),
    )
    await renderApp(`/admin/integrations/${CLIENT.id}`)
    const form = await screen.findByRole('form', { name: 'Create key' })
    await userEvent.type(within(form).getByLabelText('Label'), 'Third')
    await userEvent.click(within(form).getByRole('button', { name: 'Create key' }))
    expect(
      await screen.findByText('A client can have at most two active keys. Revoke one first.'),
    ).toBeInTheDocument()
  })
})

describe('FR-INT-04 IDs in other systems on record pages', () => {
  const REFERENCE: Schemas['ExternalReferenceOut'] = {
    entity_type: 'organization',
    entity_id: ORG.id,
    system: ERP,
    external_id: 'C-100234',
    url: 'https://erp.example.test/customers/C-100234',
    updated_at: '2026-11-17T09:00:00Z',
    updated_by: null,
  }

  beforeEach(() => {
    referenceLists()
    const detail = {
      ...ORG,
      counts: {
        contacts: 0,
        open_leads: 0,
        open_opportunities: 0,
        open_pipeline_value: '0.00',
        currency: 'EUR' as const,
      },
    }
    server.use(
      http.get(`*/api/v1/organizations/${ORG.id}`, () => HttpResponse.json(detail)),
      http.get(`*/api/v1/organizations/${ORG.id}/contacts`, () => HttpResponse.json(page([]))),
      http.get(`*/api/v1/organizations/${ORG.id}/leads`, () => HttpResponse.json(page([]))),
      http.get(`*/api/v1/organizations/${ORG.id}/opportunities`, () => HttpResponse.json(page([]))),
    )
  })

  it('AC4 shows a stored ID as a link to the other system', async () => {
    signedInAs(REP_ME)
    server.use(
      http.get(`*/api/v1/organizations/${ORG.id}/external-references`, () =>
        HttpResponse.json([REFERENCE]),
      ),
    )
    await renderApp(`/organizations/${ORG.id}`)
    const link = await screen.findByRole('link', { name: 'C-100234' })
    expect(link).toHaveAttribute('href', REFERENCE.url)
    expect(screen.queryByRole('form', { name: 'Add an ID in another system' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull()
  })

  it('is hidden from non-Admins when there is nothing to show', async () => {
    signedInAs(REP_ME)
    await renderApp(`/organizations/${ORG.id}`)
    expect(await screen.findByRole('heading', { name: ORG.name })).toBeInTheDocument()
    expect(screen.queryByText('IDs in other systems')).toBeNull()
  })

  it('lets an Admin add and remove an ID', async () => {
    signedInAs(ADMIN_ME)
    let stored: Schemas['ExternalReferenceOut'][] = []
    let put: { system: string; body: unknown } | null = null
    server.use(
      http.get('*/api/v1/reference/external-systems', () => HttpResponse.json([ERP_ITEM])),
      http.get(`*/api/v1/organizations/${ORG.id}/external-references`, () =>
        HttpResponse.json(stored),
      ),
      http.put(
        `*/api/v1/organizations/${ORG.id}/external-references/:system`,
        async ({ params, request }) => {
          put = { system: String(params['system']), body: await request.json() }
          stored = [{ ...REFERENCE, url: null }]
          return HttpResponse.json(stored[0])
        },
      ),
      http.delete(`*/api/v1/organizations/${ORG.id}/external-references/erp`, () => {
        stored = []
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await renderApp(`/organizations/${ORG.id}`)
    expect(await screen.findByText('No IDs in other systems.')).toBeInTheDocument()
    const form = screen.getByRole('form', { name: 'Add an ID in another system' })
    await userEvent.selectOptions(await within(form).findByLabelText('System'), 'erp')
    await userEvent.type(within(form).getByLabelText('ID'), ' C-100234 ')
    await userEvent.click(within(form).getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('C-100234')).toBeInTheDocument()
    expect(put).toEqual({ system: 'erp', body: { external_id: 'C-100234', url: null } })

    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }))
    expect(await screen.findByText('No IDs in other systems.')).toBeInTheDocument()
  })
})

const SUBSCRIPTION: Schemas['WebhookSubscriptionOut'] = {
  id: '01930000-0000-7000-8000-0000000006s1',
  client_id: CLIENT.id,
  url: 'https://hooks.erp.example.test/crm',
  event_types: ['opportunity.closed_won'],
  is_active: true,
  suspended_at: null,
  failing_since: null,
  previous_secret_valid_until: null,
  deliveries_24h: { succeeded: 5, pending: 1, retrying: 2, failed: 1 },
  created_at: '2026-11-17T09:00:00Z',
  updated_at: '2026-11-17T09:00:00Z',
}

const DELIVERY: Schemas['WebhookDeliveryDetail'] = {
  id: '01930000-0000-7000-8000-0000000006d1',
  subscription_id: SUBSCRIPTION.id,
  client_id: CLIENT.id,
  event_id: 'evt_0193f1c2',
  event_type: 'opportunity.closed_won',
  entity_type: 'opportunity',
  entity_id: '01930000-0000-7000-8000-0000000000f1',
  occurred_at: '2026-11-17T09:00:00Z',
  status: 'retrying',
  attempt_count: 1,
  next_attempt_at: '2026-11-17T09:01:00Z',
  last_status_code: 500,
  last_error: null,
  delivered_at: null,
  created_at: '2026-11-17T09:00:00Z',
  url: SUBSCRIPTION.url,
  attempts: [
    {
      number: 1,
      attempted_at: '2026-11-17T09:00:01Z',
      duration_ms: 87,
      status_code: 500,
      error: null,
      response_excerpt: '{"error": "down"}',
    },
  ],
}

describe('FR-INT-07 webhook subscriptions', () => {
  it('subscribes an endpoint and shows the signing secret once', async () => {
    signedInAs(ADMIN_ME)
    let body: Record<string, unknown> = {}
    onClient(CLIENT)
    server.use(
      http.post(
        `*/api/v1/integration-clients/${CLIENT.id}/webhook-subscriptions`,
        async ({ request }) => {
          body = (await request.json()) as Record<string, unknown>
          return HttpResponse.json(
            { ...SUBSCRIPTION, secret: 'whsec_once-only-value' },
            { status: 201 },
          )
        },
      ),
    )
    await renderApp(`/admin/integrations/${CLIENT.id}`)
    expect(await screen.findByText('No subscriptions yet.')).toBeInTheDocument()
    const form = screen.getByRole('form', { name: 'New subscription' })
    await userEvent.type(within(form).getByLabelText('Endpoint URL'), SUBSCRIPTION.url)
    await userEvent.click(within(form).getByRole('checkbox', { name: 'opportunity.closed_won' }))
    await userEvent.click(within(form).getByRole('button', { name: 'Subscribe' }))
    expect(await screen.findByText('Copy the signing secret now')).toBeInTheDocument()
    expect(screen.getByDisplayValue('whsec_once-only-value')).toBeInTheDocument()
    expect(body).toEqual({
      url: SUBSCRIPTION.url,
      event_types: ['opportunity.closed_won'],
      is_active: true,
    })
  })

  it('AC5 shows the URL rule when the host is not allowed', async () => {
    signedInAs(ADMIN_ME)
    onClient(CLIENT)
    server.use(
      http.post(`*/api/v1/integration-clients/${CLIENT.id}/webhook-subscriptions`, () =>
        problem(422, 'webhook.url_not_allowed', {
          errors: [{ field: 'url', code: 'webhook.url_not_allowed' }],
        }),
      ),
    )
    await renderApp(`/admin/integrations/${CLIENT.id}`)
    const form = await screen.findByRole('form', { name: 'New subscription' })
    await userEvent.type(within(form).getByLabelText('Endpoint URL'), 'https://evil.test/h')
    await userEvent.click(within(form).getByRole('checkbox', { name: 'All events' }))
    await userEvent.click(within(form).getByRole('button', { name: 'Subscribe' }))
    expect(within(form).getByLabelText('Endpoint URL')).toBeInTheDocument()
    await waitFor(() => {
      expect(within(form).getByLabelText('Endpoint URL')).toHaveAttribute('aria-invalid', 'true')
    })
  })

  it('lists a subscription, rotates its secret and queues a test event', async () => {
    signedInAs(ADMIN_ME)
    onClient(CLIENT, [], [SUBSCRIPTION])
    server.use(
      http.post(`*/api/v1/webhook-subscriptions/${SUBSCRIPTION.id}/rotate-secret`, () =>
        HttpResponse.json({
          secret: 'whsec_rotated',
          previous_secret_valid_until: '2026-11-18T09:00:00Z',
        }),
      ),
      http.post(`*/api/v1/webhook-subscriptions/${SUBSCRIPTION.id}/test`, () =>
        HttpResponse.json({ ...DELIVERY, event_type: 'ping', status: 'pending' }, { status: 202 }),
      ),
      http.get(`*/api/v1/webhook-deliveries/${DELIVERY.id}`, () =>
        HttpResponse.json({ ...DELIVERY, status: 'succeeded', event_type: 'ping' }),
      ),
    )
    const { router } = await renderApp(`/admin/integrations/${CLIENT.id}`)
    const item = await screen.findByRole('listitem', { name: SUBSCRIPTION.url })
    expect(
      within(item).getByText('Last 24 hours: 5 delivered, 3 failing, 1 waiting'),
    ).toBeInTheDocument()
    await userEvent.click(within(item).getByRole('button', { name: 'Rotate secret' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }))
    expect(await screen.findByDisplayValue('whsec_rotated')).toBeInTheDocument()

    await userEvent.click(within(item).getByRole('button', { name: 'Send test event' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/admin/integrations/deliveries/${DELIVERY.id}`)
    })
    expect(await screen.findByText('Delivered')).toBeInTheDocument()
  })

  it('resumes a suspended subscription', async () => {
    signedInAs(ADMIN_ME)
    const suspended = { ...SUBSCRIPTION, suspended_at: '2026-11-17T09:00:00Z' }
    onClient(CLIENT, [], [suspended])
    let body: Record<string, unknown> = {}
    server.use(
      http.patch(`*/api/v1/webhook-subscriptions/${SUBSCRIPTION.id}`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(SUBSCRIPTION)
      }),
    )
    await renderApp(`/admin/integrations/${CLIENT.id}`)
    const item = await screen.findByRole('listitem', { name: SUBSCRIPTION.url })
    expect(within(item).getByText('Suspended')).toBeInTheDocument()
    await userEvent.click(within(item).getByRole('button', { name: 'Resume' }))
    await waitFor(() => {
      expect(body).toEqual({ is_active: true })
    })
  })
})

describe('FR-INT-12 delivery log', () => {
  it('filters by status in the URL and opens a delivery with its attempts', async () => {
    signedInAs(ADMIN_ME)
    const requests: string[] = []
    server.use(
      http.get('*/api/v1/integration-clients', () => HttpResponse.json([CLIENT])),
      http.get('*/api/v1/webhook-deliveries', ({ request }) => {
        requests.push(new URL(request.url).search)
        return HttpResponse.json({ items: [DELIVERY], total: 1, page: 1, page_size: 25 })
      }),
      http.get(`*/api/v1/webhook-deliveries/${DELIVERY.id}`, () => HttpResponse.json(DELIVERY)),
    )
    const { router } = await renderApp('/admin/integrations/deliveries')
    const table = await screen.findByRole('table', { name: 'Webhook deliveries' })
    expect(await within(table).findByText('ERP (read-only)')).toBeInTheDocument()
    expect(within(table).getByText('Retrying')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'failed')
    await waitFor(() => {
      expect(router.state.location.search).toBe('?status=failed')
    })
    expect(requests.at(-1)).toContain('status=failed')

    await userEvent.click(within(table).getByRole('link', { name: /2026/ }))
    expect(await screen.findByText('{"error": "down"}')).toBeInTheDocument()
    expect(screen.getByText(DELIVERY.event_id)).toBeInTheDocument()
  })

  it('AC3 redelivers a delivery', async () => {
    signedInAs(ADMIN_ME)
    let redelivered = false
    server.use(
      http.get(`*/api/v1/webhook-deliveries/${DELIVERY.id}`, () =>
        HttpResponse.json({ ...DELIVERY, status: 'failed' }),
      ),
      http.post(`*/api/v1/webhook-deliveries/${DELIVERY.id}/redeliver`, () => {
        redelivered = true
        return HttpResponse.json({ ...DELIVERY, id: 'new', status: 'pending' }, { status: 202 })
      }),
    )
    await renderApp(`/admin/integrations/deliveries/${DELIVERY.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Redeliver' }))
    expect(await screen.findByText('Delivery queued again.')).toBeInTheDocument()
    expect(redelivered).toBe(true)
  })
})

describe('FR-INT-08 failing-delivery alert', () => {
  it('shows a badge on the navigation and a banner in the admin area', async () => {
    signedInAs(ADMIN_ME)
    const failing = {
      ...CLIENT,
      webhooks: { subscriptions: 1, failing_deliveries: 3, suspended_subscriptions: 1 },
    }
    server.use(http.get('*/api/v1/integration-clients', () => HttpResponse.json([failing])))
    await renderApp('/admin/integrations')
    expect(await screen.findByLabelText('4 webhook problems')).toBeInTheDocument()
    expect(screen.getByText('Webhook deliveries are failing')).toBeInTheDocument()
    expect(screen.getByText(/3 failing deliveries, 1 suspended subscriptions/)).toBeInTheDocument()
    expect(screen.getByText('3 failing')).toBeInTheDocument()
  })

  it('is not shown without problems', async () => {
    signedInAs(ADMIN_ME)
    server.use(http.get('*/api/v1/integration-clients', () => HttpResponse.json([CLIENT])))
    await renderApp('/admin/integrations')
    expect(await screen.findByRole('table', { name: 'Integrations' })).toBeInTheDocument()
    expect(screen.queryByText('Webhook deliveries are failing')).toBeNull()
  })
})
