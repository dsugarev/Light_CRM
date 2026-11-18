import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import i18n from '@/i18n'
import { ADMIN_ME, signedInAs, USER } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

import { AuditDiff } from './AuditDiff'

const SUMMARY = {
  id: 'e1',
  occurred_at: '2026-11-17T09:00:00Z',
  actor: { type: 'user', id: ADMIN_ME.id, name: 'Ada Admin' },
  action: 'organization.updated',
  entity_type: 'organization',
  entity_id: '01930000-0000-7000-8000-0000000000aa',
  ip: '10.0.0.5',
}
const LONG = 'Дълго описание на организацията, '.repeat(40)
const ENTRY = {
  ...SUMMARY,
  before: { name: 'Акме ЕООД', city: 'София', description: 'Short' },
  after: { name: 'Акме Груп ЕООД', city: 'София', description: LONG },
  details: null,
  request_id: 'req-9',
}

function sofiaDay(daysAgo: number) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Sofia' }).format(
    new Date(Date.now() - daysAgo * 86_400_000),
  )
}

function auditApi() {
  const requests: URLSearchParams[] = []
  server.use(
    http.get('*/api/v1/audit-log', ({ request }) => {
      requests.push(new URL(request.url).searchParams)
      return HttpResponse.json({ items: [SUMMARY], total: 1, page: 1, page_size: 50 })
    }),
    http.get('*/api/v1/audit-log/e1', () => HttpResponse.json(ENTRY)),
    http.get('*/api/v1/users', () =>
      HttpResponse.json({ items: [USER], total: 1, page: 1, page_size: 100 }),
    ),
  )
  return requests
}

beforeEach(() => {
  signedInAs(ADMIN_ME)
})

describe('UX-10 audit log viewer', () => {
  it('UX-10 filters by user and record type', async () => {
    const requests = auditApi()
    const { router } = await renderApp('/admin/audit-log')
    await screen.findByRole('table')
    await userEvent.selectOptions(await screen.findByLabelText('User'), USER.id)
    await userEvent.selectOptions(screen.getByLabelText('Record type'), 'organization')
    await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    await waitFor(() => {
      expect(requests.at(-1)?.get('actor_id')).toBe(USER.id)
    })
    expect(requests.at(-1)?.get('entity_type')).toBe('organization')
    expect(router.state.location.search).toBe(`?actor_id=${USER.id}&entity_type=organization`)
  })

  it.each([
    ['Today', 0],
    ['Last 7 days', 6],
    ['Last 30 days', 29],
  ])('UX-10 the %s preset sets the date range', async (label, days) => {
    const requests = auditApi()
    const { router } = await renderApp('/admin/audit-log')
    await screen.findByRole('table')
    await userEvent.click(screen.getByRole('button', { name: label }))
    await waitFor(() => {
      expect(router.state.location.search).toBe(`?from=${sofiaDay(days)}&to=${sofiaDay(0)}`)
    })
    await waitFor(() => {
      expect(requests.at(-1)?.get('occurred_at_from')).toBeTruthy()
    })
    expect(screen.getByLabelText('From')).toHaveValue(sofiaDay(days))
  })

  it('UX-10 opens an entry in a drawer with changes side by side', async () => {
    auditApi()
    const { router } = await renderApp('/admin/audit-log')
    await userEvent.click(await screen.findByRole('link', { name: /^Open entry 17 Nov 2026/ }))
    expect(router.state.location.search).toBe('?entry=e1')
    const drawer = await screen.findByRole('dialog', { name: 'Organization updated' })
    const changes = await within(drawer).findByRole('table', { name: 'Changes' })
    const name = within(changes).getByRole('rowheader', { name: /name/ }).closest('tr')
    expect(name).toHaveAttribute('data-changed', 'true')
    expect(name).toHaveTextContent('Акме ЕООД')
    expect(name).toHaveTextContent('Акме Груп ЕООД')
    expect(within(changes).getByRole('rowheader', { name: 'name (changed)' })).toBeInTheDocument()
    const city = within(changes).getByRole('rowheader', { name: 'city' }).closest('tr')
    expect(city).not.toHaveAttribute('data-changed')
    // A long Cyrillic value is shown in full and wraps.
    expect(within(changes).getByText(LONG.trim(), { exact: false })).toBeInTheDocument()
    expect(within(drawer).getByText('req-9')).toBeInTheDocument()

    await userEvent.keyboard('{Escape}')
    await waitFor(() => {
      expect(router.state.location.search).toBe('')
    })
  })

  it('UX-10 opens the drawer from a shared link, in Bulgarian too', async () => {
    signedInAs({ ...ADMIN_ME, locale: 'bg' })
    auditApi()
    await renderApp('/admin/audit-log?entry=e1', 'bg')
    const drawer = await screen.findByRole('dialog', { name: 'Променена организация' })
    expect(await within(drawer).findByRole('table', { name: 'Промени' })).toBeInTheDocument()
    expect(within(drawer).getByText('Организация')).toBeInTheDocument()
  })
})

describe('UX-10 diff', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('UX-10 shows a created record with nothing before', () => {
    render(<AuditDiff before={null} after={{ name: 'Нова ЕООД' }} />)
    const row = screen.getByRole('rowheader', { name: 'name (changed)' }).closest('tr')
    expect(row).toHaveTextContent('—')
    expect(row).toHaveTextContent('Нова ЕООД')
  })

  it('UX-10 shows nested values as formatted JSON', () => {
    render(<AuditDiff before={{ tags: ['a'] }} after={{ tags: ['a', 'b'] }} />)
    expect(screen.getByText(/"b"/)).toBeInTheDocument()
  })

  it('UX-10 falls back to formatted JSON when the values are not field maps', () => {
    render(<AuditDiff before={['x']} after={['x', 'y']} />)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByLabelText('After')).toHaveTextContent('"y"')
  })
})

describe('UX-10 diff of a created record', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('UX-10 does not flag fields that stay empty', () => {
    render(<AuditDiff before={null} after={{ name: 'Нова ЕООД', city: null }} />)
    const city = screen.getByRole('rowheader', { name: 'city' }).closest('tr')
    expect(city).not.toHaveAttribute('data-changed')
  })
})

describe('FN-07 audit log export', () => {
  it('FN-07 exports the log with the current filters and without paging', async () => {
    auditApi()
    let url = ''
    server.use(
      http.get('*/api/v1/audit-log/export', ({ request }) => {
        url = request.url
        return new HttpResponse('﻿time\r\n', {
          headers: {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename="audit-log.csv"',
          },
        })
      }),
    )
    const created = vi.fn(() => 'blob:audit')
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    await renderApp(
      `/admin/audit-log?actor_id=${USER.id}&entity_type=lead&action=lead.updated&from=2026-11-01&to=2026-11-17&page=3`,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Export CSV' }))
    await waitFor(() => {
      expect(click).toHaveBeenCalled()
    })
    const params = new URL(url).searchParams
    expect(params.get('actor_id')).toBe(USER.id)
    expect(params.get('entity_type')).toBe('lead')
    expect(params.get('action')).toBe('lead.updated')
    // Sofia days as UTC instants, as for the list.
    expect(params.get('occurred_at_from')).toBe('2026-10-31T22:00:00.000Z')
    expect(params.get('occurred_at_to')).toBe('2026-11-17T21:59:59.000Z')
    expect(params.get('format')).toBe('csv')
    expect(params.has('page')).toBe(false)
    expect(created).toHaveBeenCalled()
    click.mockRestore()
  })
})
