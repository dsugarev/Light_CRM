import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { Schemas } from '@/api/client'
import { LEAD, leadLists, page, REP_ME, signedInAs, STAGES, summary } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

const DASHBOARD: Schemas['Dashboard'] = {
  from_date: '2026-01-01',
  to_date: '2026-12-31',
  pipeline: {
    currency: 'EUR',
    stages: [
      { stage: summary(STAGES[0]), count: 2, total_amount: '4000.00', weighted_amount: '400.00' },
      { stage: summary(STAGES[3]), count: 1, total_amount: '3000.00', weighted_amount: '2250.00' },
    ],
    count: 3,
    total_amount: '7000.00',
    weighted_amount: '2650.00',
  },
  forecast: {
    currency: 'EUR',
    months: [
      { month: '2026-11', count: 1, total_amount: '1000.00', weighted_amount: '100.00' },
      { month: '2026-12', count: 2, total_amount: '6000.00', weighted_amount: '2550.00' },
    ],
    weighted_amount: '2650.00',
  },
  lead_conversion: {
    created: 5,
    qualified: 3,
    converted: 2,
    disqualified: 1,
    conversion_rate: 0.4,
  },
  win_loss: {
    won_count: 2,
    won_amount: '3000.00',
    lost_count: 3,
    lost_amount: '1500.00',
    win_rate: 0.4,
  },
  my_tasks: { open: 4, overdue: 1 },
}

describe('FR-REP-01 dashboard', () => {
  it('shows pipeline, forecast, rates and my tasks; the owner filter is in the URL', async () => {
    signedInAs(REP_ME)
    const requests: string[] = []
    server.use(
      http.get('*/api/v1/reports/dashboard', ({ request }) => {
        requests.push(new URL(request.url).search)
        return HttpResponse.json(DASHBOARD)
      }),
    )
    const { router } = await renderApp('/')
    expect(await screen.findByText('€7,000.00')).toBeInTheDocument()
    expect(screen.getByText('Weighted €2,650.00')).toBeInTheDocument()
    expect(screen.getByText('2 of 5 leads converted')).toBeInTheDocument()
    expect(screen.getByText('2 won, 3 lost')).toBeInTheDocument()
    expect(screen.getAllByText('40%')).toHaveLength(2)
    expect(screen.getByRole('link', { name: '4' })).toHaveAttribute('href', '/tasks')
    expect(screen.getByText('1 overdue')).toBeInTheDocument()
    const stages = screen.getByRole('table', { name: 'Open pipeline by stage' })
    expect(
      within(stages).getByRole('row', { name: /Negotiation 1 €3,000.00 €2,250.00/ }),
    ).toBeInTheDocument()
    expect(requests[0]).toContain('from=')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Owner' }), 'me')
    await waitFor(() => {
      expect(router.state.location.search).toContain('owner=me')
    })
    await waitFor(() => {
      expect(requests.at(-1)).toContain('owner_id=me')
    })
  })

  it('FR-I18N-01 in Bulgarian', async () => {
    signedInAs({ ...REP_ME, locale: 'bg' })
    server.use(http.get('*/api/v1/reports/dashboard', () => HttpResponse.json(DASHBOARD)))
    await renderApp('/', 'bg')
    expect(await screen.findByText('Табло за управление')).toBeInTheDocument()
    expect(await screen.findByText('2 от 5 превърнати')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Отворени възможности по етапи' })).toHaveTextContent(
      'Преговори',
    )
  })

  it('FR-REP-01 loop 3: each KPI card opens the list behind its figure', async () => {
    signedInAs(REP_ME)
    server.use(http.get('*/api/v1/reports/dashboard', () => HttpResponse.json(DASHBOARD)))
    await renderApp('/')
    const pipeline = await screen.findByRole('link', { name: 'Open pipeline' })
    expect(pipeline).toHaveAttribute('href', '/opportunities/board')
    expect(screen.getByRole('link', { name: 'Lead conversion rate' })).toHaveAttribute(
      'href',
      '/leads',
    )
    expect(screen.getByRole('link', { name: 'Win rate' })).toHaveAttribute(
      'href',
      '/reports/win-loss',
    )
    // The link covers its card, and the card lifts on hover and rings on keyboard focus.
    expect(pipeline).toHaveClass('after:absolute', 'after:inset-0')
    const card = pipeline.closest('[data-slot="card"]')
    expect(card).toHaveClass('relative', 'hover:-translate-y-0.5', 'has-[a:focus-visible]:ring-2')
    expect(screen.getByRole('link', { name: '4' })).toHaveClass('after:inset-0')
  })
})

describe('FR-REP-03 win/loss report', () => {
  it('groups by loss reason with a total row and regroups by month', async () => {
    signedInAs(REP_ME)
    const requests: string[] = []
    server.use(
      http.get('*/api/v1/reports/win-loss', ({ request }) => {
        requests.push(new URL(request.url).search)
        return HttpResponse.json({
          currency: 'EUR',
          from_date: '2026-01-01',
          to_date: '2026-12-31',
          group_by: 'loss_reason',
          totals: DASHBOARD.win_loss,
          groups: [
            {
              group: { key: 'r1', name_en: 'Price', name_bg: 'Цена' },
              won_count: 0,
              won_amount: '0.00',
              lost_count: 2,
              lost_amount: '1200.00',
              win_rate: 0,
            },
            {
              group: { key: 'none', name_en: null, name_bg: null },
              won_count: 2,
              won_amount: '3000.00',
              lost_count: 0,
              lost_amount: '0.00',
              win_rate: 1,
            },
          ],
        })
      }),
    )
    await renderApp('/reports/win-loss')
    const table = await screen.findByRole('table', { name: 'Win/loss report' })
    expect(
      within(table).getByRole('row', { name: /Price 0 €0.00 2 €1,200.00 0%/ }),
    ).toBeInTheDocument()
    expect(within(table).getByRole('row', { name: /Not set \(won\) 2/ })).toBeInTheDocument()
    expect(
      within(table).getByRole('row', { name: /Total 2 €3,000.00 3 €1,500.00 40%/ }),
    ).toBeInTheDocument()
    expect(requests[0]).toContain('group_by=loss_reason')
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Group by' }), 'month')
    await waitFor(() => {
      expect(requests.at(-1)).toContain('group_by=month')
    })
  })
})

describe('FR-REP-02 export', () => {
  beforeEach(() => {
    leadLists()
    server.use(http.get('*/api/v1/leads', () => HttpResponse.json(page([LEAD]))))
  })

  it('downloads the list with its filters and without paging', async () => {
    signedInAs(REP_ME)
    let url = ''
    server.use(
      http.get('*/api/v1/leads/export', ({ request }) => {
        url = request.url
        return new HttpResponse('﻿title\r\n', {
          headers: {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename="leads-2026-11-17.csv"',
          },
        })
      }),
    )
    const created = vi.fn(() => 'blob:export')
    const revoked = vi.fn()
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: created, revokeObjectURL: revoked }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    await renderApp('/leads?status=qualified&page=2')
    await userEvent.click(await screen.findByRole('button', { name: 'Export CSV' }))
    await waitFor(() => {
      expect(click).toHaveBeenCalled()
    })
    const params = new URL(url).searchParams
    expect(params.get('status')).toBe('qualified')
    expect(params.get('format')).toBe('csv')
    expect(params.has('page')).toBe(false)
    expect(created).toHaveBeenCalled()
    click.mockRestore()
  })

  it('explains when the export is too large', async () => {
    signedInAs(REP_ME)
    server.use(
      http.get('*/api/v1/leads/export', () =>
        problem(422, 'export.too_many_rows', { rows: 60000, limit: 50000 }),
      ),
    )
    await renderApp('/leads')
    await userEvent.click(await screen.findByRole('button', { name: 'Export XLSX' }))
    expect(
      await screen.findByText('The export has more than 50,000 rows. Narrow the filters.'),
    ).toBeInTheDocument()
  })
})
