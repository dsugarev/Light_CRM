import { render, screen } from '@testing-library/react'

import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'

// WCAG 2.1.1 (axe scrollable-region-focusable): a table that scrolls sideways can be
// reached and scrolled by keyboard; one that fits adds no tab stop.

function stubLayout(scrollWidth: number, clientWidth: number) {
  vi.spyOn(HTMLElement.prototype, 'scrollWidth', 'get').mockReturnValue(scrollWidth)
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(clientWidth)
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn()
      disconnect = vi.fn()
    },
  )
}

function renderTable() {
  render(
    <Table aria-label="Figures">
      <TableBody>
        <TableRow>
          <TableCell>1</TableCell>
        </TableRow>
      </TableBody>
    </Table>,
  )
  return screen.getByRole('table', { name: 'Figures' }).parentElement
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('NFR-10 sideways-scrolling tables are keyboard reachable', () => {
  it('NFR-10 a table wider than its container makes the container focusable', () => {
    stubLayout(900, 600)
    expect(renderTable()).toHaveAttribute('tabindex', '0')
  })

  it('NFR-10 a table that fits adds no tab stop', () => {
    stubLayout(600, 600)
    expect(renderTable()).not.toHaveAttribute('tabindex')
  })
})
