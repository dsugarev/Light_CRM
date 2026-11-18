import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { CONTACT, referenceLists, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

// UX-03: pages render their heading only through PageHeader (or AuthCard when signed out).
const sources = import.meta.glob<string>(
  ['/src/**/*.tsx', '!/src/**/*.test.tsx', '!/src/test/**'],
  { query: '?raw', import: 'default', eager: true },
)
const HEADER_COMPONENTS = ['/src/components/PageHeader.tsx', '/src/components/AuthCard.tsx']

describe('UX-03 page header', () => {
  beforeEach(() => {
    referenceLists()
  })

  it('UX-03 no page renders its own h1', () => {
    const adHoc = Object.entries(sources)
      .filter(([file, text]) => !HEADER_COMPONENTS.includes(file) && /<h1[\s>]/.test(text))
      .map(([file]) => file)
    expect(adHoc).toEqual([])
  })

  it('UX-03 record pages show breadcrumbs back to their list', async () => {
    signedInAs(REP_ME)
    server.use(http.get(`*/api/v1/contacts/${CONTACT.id}`, () => HttpResponse.json(CONTACT)))
    await renderApp(`/contacts/${CONTACT.id}`)
    const trail = await screen.findByRole('navigation', { name: 'Breadcrumbs' })
    expect(within(trail).getByRole('link', { name: 'Contacts' })).toHaveAttribute(
      'href',
      '/contacts',
    )
    expect(within(trail).getByText(CONTACT.full_name)).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('heading', { level: 1, name: CONTACT.full_name })).toBeInTheDocument()
  })

  it('UX-03 edit pages lead back through the record, in Bulgarian too', async () => {
    signedInAs({ ...REP_ME, locale: 'bg' })
    server.use(http.get(`*/api/v1/contacts/${CONTACT.id}`, () => HttpResponse.json(CONTACT)))
    await renderApp(`/contacts/${CONTACT.id}/edit`, 'bg')
    const trail = await screen.findByRole('navigation', { name: 'Навигационна пътека' })
    const links = within(trail).getAllByRole('link')
    expect(links.map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['Контакти', '/contacts'],
      [CONTACT.full_name, `/contacts/${CONTACT.id}`],
    ])
  })

  it('UX-03 list pages have no breadcrumbs but keep their actions', async () => {
    signedInAs(REP_ME)
    await renderApp('/leads')
    expect(await screen.findByRole('heading', { level: 1, name: 'Leads' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Breadcrumbs' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'New lead' })).toBeInTheDocument()
  })
})
