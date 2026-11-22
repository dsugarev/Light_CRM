/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { delay, http, HttpResponse } from 'msw'

import { DataTable, type Column } from '@/components/DataTable'
import { LEAD, leadLists, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

// Loop 2, iteration 3: interface dynamics. jsdom runs no CSS animations, so these tests
// check the states that drive them (busy, page key) and the motion rules in the theme.

// Read from disk: Vitest's CSS handling empties `?raw` imports of a stylesheet.
const themeCss = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')

interface Row {
  id: string
  name: string
}
const columns: Column<Row>[] = [{ key: 'name', header: 'Name', cell: (row) => row.name }]

function table(busy: boolean) {
  return (
    <DataTable
      caption="Things"
      columns={columns}
      rows={[{ id: '1', name: 'Acme' }]}
      rowKey={(row) => row.id}
      sort="name"
      onSort={() => undefined}
      busy={busy}
    />
  )
}

describe('UX-04 busy lists (loop 2)', () => {
  it('UX-04 a busy table is marked aria-busy, dims its rows and shows the progress bar', () => {
    render(table(true))
    const grid = screen.getByRole('table', { name: 'Things' })
    expect(grid).toHaveAttribute('aria-busy', 'true')
    expect(grid.querySelector('tbody')).toHaveAttribute('data-busy', 'true')
    expect(screen.getByTestId('table-busy')).toHaveAttribute('aria-hidden', 'true')
  })

  it('UX-04 an idle table has no busy state', () => {
    render(table(false))
    const grid = screen.getByRole('table', { name: 'Things' })
    expect(grid).not.toHaveAttribute('aria-busy')
    expect(grid.querySelector('tbody')).not.toHaveAttribute('data-busy')
    expect(screen.queryByTestId('table-busy')).toBeNull()
  })

  it('FR-LEAD-05 the lead list shows it is updating while the next page loads', async () => {
    leadLists()
    signedInAs(REP_ME)
    let releaseSecondPage: () => void = () => undefined
    const secondPageGate = new Promise<void>((resolve) => {
      releaseSecondPage = resolve
    })
    server.use(
      http.get('*/api/v1/leads', async ({ request }) => {
        const pageNo = new URL(request.url).searchParams.get('page') ?? '1'
        if (pageNo === '2') {
          await secondPageGate
          return HttpResponse.json({
            items: [{ ...LEAD, id: 'second-page-lead', title: 'Second page lead' }],
            total: 30,
            page: 2,
            page_size: 25,
          })
        }
        return HttpResponse.json({ items: [LEAD], total: 30, page: 1, page_size: 25 })
      }),
    )
    await renderApp('/leads')
    const grid = await screen.findByRole('table', { name: 'Leads' })
    expect(grid).not.toHaveAttribute('aria-busy')

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => {
      expect(screen.getByRole('table', { name: 'Leads' })).toHaveAttribute('aria-busy', 'true')
    })
    // The previous rows stay visible meanwhile.
    expect(screen.getByRole('link', { name: LEAD.title })).toBeInTheDocument()

    releaseSecondPage()
    await screen.findByRole('link', { name: 'Second page lead' })
    expect(screen.getByRole('table', { name: 'Leads' })).not.toHaveAttribute('aria-busy')
  })
})

describe('UX-04 page transitions (loop 2)', () => {
  it('UX-04 a new page enters when the address changes, not when only the search changes', async () => {
    leadLists()
    signedInAs(REP_ME)
    server.use(
      http.get('*/api/v1/leads', async () => {
        await delay(10)
        return HttpResponse.json({ items: [LEAD], total: 1, page: 1, page_size: 25 })
      }),
    )
    const { router } = await renderApp('/leads')
    await screen.findByRole('table', { name: 'Leads' })
    const first = screen.getByTestId('page-transition')
    expect(first.className).toMatch(/\banimate-in\b/)
    expect(first.className).toMatch(/\bslide-in-from-bottom-1\b/)
    // Movement only: a fade would lower text contrast while it runs (NFR-10).
    expect(first.className).not.toMatch(/\bfade-in/)

    await router.navigate('/leads?q=acme')
    await screen.findByRole('table', { name: 'Leads' })
    expect(screen.getByTestId('page-transition')).toBe(first)

    await router.navigate('/')
    await waitFor(() => {
      expect(screen.getByTestId('page-transition')).not.toBe(first)
    })
  })
})

describe('WCAG 2.3.3 reduced motion (loop 2)', () => {
  it('WCAG 2.3.3 the theme stops animations and transitions when the user asks for less motion', () => {
    const block = /@media \(prefers-reduced-motion: reduce\) \{([\s\S]*?)\n\}/.exec(themeCss)?.[1]
    expect(block).toBeDefined()
    expect(block).toContain('animation-duration: 0.01ms !important')
    expect(block).toContain('transition-duration: 0.01ms !important')
    expect(block).toMatch(/\.busy-bar \{[^}]*animation: none !important/)
  })

  it('UX-04 the busy bar appears only after a short delay, so quick answers do not flicker', () => {
    expect(themeCss).toMatch(
      /@utility busy-track \{\s*animation: busy-appear 150ms ease-out 200ms both;/,
    )
  })
})
