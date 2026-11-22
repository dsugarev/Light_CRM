import { render, screen } from '@testing-library/react'

import { detailListClass } from '@/components/detailList'
import { FilterBar } from '@/components/FilterBar'
import { Pagination } from '@/components/Pagination'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'

// NFR-11 ("usable down to tablet width"), loop 2. jsdom has no layout or media queries,
// so these tests pin the responsive classes; the real rendering was measured in Chromium
// with touch emulation (docs/loop_result.md, loop 2 iteration 2).

const SIZES = ['default', 'xs', 'sm', 'lg', 'icon', 'icon-xs', 'icon-sm', 'icon-lg'] as const

describe('NFR-11 touch targets (loop 2)', () => {
  it.each(SIZES)('NFR-11 a %s button grows on a coarse pointer', (size) => {
    render(<Button size={size}>{size}</Button>)
    expect(screen.getByRole('button').className).toMatch(/\bpointer-coarse:(h|size)-(8|10|11)\b/)
  })

  it('NFR-11 text inputs grow to 44 px on a coarse pointer', () => {
    render(<Input aria-label="field" />)
    expect(screen.getByRole('textbox').className).toMatch(/\bpointer-coarse:h-11\b/)
  })
})

describe('NFR-11 narrow screens (loop 2)', () => {
  it('NFR-11 the search box never needs more than the screen width', () => {
    const { container } = render(
      <FilterBar>
        <input aria-label="search" />
      </FilterBar>,
    )
    const bar = container.firstElementChild
    expect(bar?.className).toContain('[&>input]:min-w-[min(20rem,100%)]')
    expect(bar?.className).not.toMatch(/\[&>input\]:min-w-80\b/)
  })

  it('NFR-11 pagination wraps instead of overflowing', () => {
    render(<Pagination page={1} pageSize={25} total={100} onPageChange={() => undefined} />)
    expect(screen.getByRole('navigation').className).toMatch(/\bflex-wrap\b/)
  })

  it('NFR-11 a sideways-scrolling table shows a scroll hint', () => {
    const { container } = render(
      <Table>
        <TableBody>
          <TableRow>
            <TableCell>cell</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    )
    const wrapper = container.querySelector('[data-slot="table-container"]')
    expect(wrapper?.className).toMatch(/\bscroll-shadow-x\b/)
    expect(wrapper?.className).toMatch(/\boverflow-x-auto\b/)
  })

  it('NFR-11 record details stack label over value below the sm breakpoint', () => {
    const cls = detailListClass()
    expect(cls).toMatch(/(^| )grid-cols-1( |$)/)
    expect(cls).toContain('sm:grid-cols-[max-content_1fr]')
    expect(cls).toContain('[&_dd]:break-words')
    expect(detailListClass('compact')).toContain('sm:gap-y-1')
  })
})

// Every record page's label/value list uses the shared classes, so none is left with
// the fixed two columns that squeeze values on a phone.
const pages = import.meta.glob<string>(['/src/features/**/*.tsx', '!/src/**/*.test.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
})

describe('NFR-11 record detail lists (loop 2)', () => {
  it('NFR-11 no page hard-codes a two-column detail list', () => {
    const offenders = Object.entries(pages)
      .filter(([, text]) => text.includes('<dl className="grid grid-cols-[max-content_1fr]'))
      .map(([file]) => file)
    expect(offenders).toEqual([])
  })

  it('NFR-11 the record pages use the shared detail list', () => {
    const users = Object.entries(pages)
      .filter(([, text]) => text.includes('detailListClass('))
      .map(([file]) => file.split('/').pop())
    expect(users).toEqual(
      expect.arrayContaining([
        'OrganizationPage.tsx',
        'OpportunityPage.tsx',
        'LeadPage.tsx',
        'ContactPages.tsx',
      ]),
    )
  })
})
