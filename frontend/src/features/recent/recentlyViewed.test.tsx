import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { CONTACT, LEAD, REP_ME, referenceLists, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

import { MAX_RECENT, readRecent, rememberRecent } from './recentRecords'

function recentCard() {
  return screen.findByRole('heading', { name: 'Recently viewed' }).then((heading) => {
    const card = heading.closest('[data-slot=card]')
    if (!(card instanceof HTMLElement)) throw new Error('no card')
    return card
  })
}

describe('recently viewed records', () => {
  beforeEach(() => {
    signedInAs(REP_ME)
    referenceLists()
    server.use(
      http.get(`*/api/v1/contacts/${CONTACT.id}`, () => HttpResponse.json(CONTACT)),
      http.get(`*/api/v1/leads/${LEAD.id}`, () => HttpResponse.json(LEAD)),
    )
  })

  it('shows nothing until a record is opened', async () => {
    await renderApp('/')
    await screen.findByRole('heading', { name: 'Welcome, Boris Rep' })
    expect(screen.queryByRole('heading', { name: 'Recently viewed' })).not.toBeInTheDocument()
  })

  it('lists opened records on the home page, newest first, without duplicates', async () => {
    const { router } = await renderApp(`/contacts/${CONTACT.id}`)
    await screen.findByRole('heading', { level: 1, name: CONTACT.full_name })
    await router.navigate(`/leads/${LEAD.id}`)
    await screen.findByRole('heading', { level: 1, name: LEAD.title })
    await router.navigate(`/contacts/${CONTACT.id}`)
    await screen.findByRole('heading', { level: 1, name: CONTACT.full_name })
    await router.navigate('/')
    const card = await recentCard()
    const links = within(card).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual([CONTACT.full_name, LEAD.title])
    expect(links[0]).toHaveAttribute('href', `/contacts/${CONTACT.id}`)
    expect(card).toHaveTextContent('Contact ·')
    expect(card).toHaveTextContent('Lead ·')
  })

  it('keeps only the latest records', () => {
    for (let i = 0; i < MAX_RECENT + 3; i += 1) {
      rememberRecent('u1', { type: 'lead', id: `l${String(i)}`, label: `Lead ${String(i)}` }, i)
    }
    const kept = readRecent('u1')
    expect(kept).toHaveLength(MAX_RECENT)
    expect(kept[0]?.label).toBe(`Lead ${String(MAX_RECENT + 2)}`)
  })

  it('keeps each user’s records apart', () => {
    rememberRecent('u1', { type: 'lead', id: 'l1', label: 'Mine' })
    expect(readRecent('u2')).toEqual([])
  })

  it('forgets a record that no longer exists', async () => {
    rememberRecent(REP_ME.id, { type: 'lead', id: 'gone', label: 'Deleted lead' })
    server.use(http.get('*/api/v1/leads/gone', () => problem(404, 'resource.not_found')))
    const { router } = await renderApp('/leads/gone')
    await screen.findByRole('alert')
    await waitFor(() => {
      expect(readRecent(REP_ME.id)).toEqual([])
    })
    await router.navigate('/')
    await screen.findByRole('heading', { name: 'Welcome, Boris Rep' })
    expect(screen.queryByText('Deleted lead')).not.toBeInTheDocument()
  })

  it('clears the list on sign-out, so a shared computer shows nothing', async () => {
    rememberRecent(REP_ME.id, { type: 'lead', id: LEAD.id, label: LEAD.title })
    server.use(http.post('*/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })))
    await renderApp('/')
    await recentCard()
    await userEvent.click(screen.getByRole('button', { name: /^Account menu: / }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Sign out' }))
    await screen.findByRole('heading', { name: 'Sign in' })
    expect(readRecent(REP_ME.id)).toEqual([])
  })

  it('labels record types in Bulgarian', async () => {
    signedInAs({ ...REP_ME, locale: 'bg' })
    rememberRecent(REP_ME.id, { type: 'opportunity', id: 'o1', label: 'Свързаност' })
    await renderApp('/', 'bg')
    const heading = await screen.findByRole('heading', { name: 'Последно отваряни' })
    expect(heading.closest('[data-slot=card]')).toHaveTextContent('Възможност ·')
  })
})
