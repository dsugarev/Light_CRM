import { cleanup, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ADMIN_ME, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'

function sidebar() {
  return within(document.getElementById('app-sidebar') ?? document.body)
}

describe('UX-02 app shell', () => {
  it('UX-02 groups the navigation by area and highlights the active route', async () => {
    signedInAs(ADMIN_ME)
    await renderApp('/organizations')
    const nav = within(await screen.findByRole('navigation', { name: 'Main navigation' }))
    expect(nav.getByRole('list', { name: 'Sales' })).toBeInTheDocument()
    const admin = nav.getByRole('list', { name: 'Administration' })
    expect(within(admin).getByRole('link', { name: 'Users' })).toBeInTheDocument()
    expect(nav.getByRole('link', { name: 'Organizations' })).toHaveAttribute('aria-current', 'page')
    expect(nav.getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
  })

  it('UX-02 shows only the routes a sales rep may open', async () => {
    signedInAs(REP_ME)
    await renderApp('/')
    const nav = within(await screen.findByRole('navigation', { name: 'Main navigation' }))
    expect(nav.getByRole('link', { name: 'Leads' })).toBeInTheDocument()
    expect(nav.queryByRole('list', { name: 'Administration' })).not.toBeInTheDocument()
  })

  it('UX-02 collapses the sidebar and remembers it for the session', async () => {
    signedInAs(ADMIN_ME)
    await renderApp('/')
    const hide = await screen.findByRole('button', { name: 'Hide navigation' })
    expect(hide).toHaveAttribute('aria-expanded', 'true')
    expect(hide).toHaveAttribute('aria-controls', 'app-sidebar')
    await userEvent.click(hide)
    expect(screen.getByRole('button', { name: 'Show navigation' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(document.getElementById('app-sidebar')).toHaveClass('hidden')
    expect(document.getElementById('app-sidebar')).not.toHaveClass('lg:block')

    cleanup()
    await renderApp('/')
    expect(await screen.findByRole('button', { name: 'Show navigation' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show navigation' }))
    expect(document.getElementById('app-sidebar')).toHaveClass('lg:block')
  })

  it('UX-02 opens the navigation drawer and closes it after navigating, in Bulgarian too', async () => {
    signedInAs({ ...REP_ME, locale: 'bg' })
    const { router } = await renderApp('/', 'bg')
    await userEvent.click(await screen.findByRole('button', { name: 'Меню' }))
    const drawer = await screen.findByRole('dialog', { name: 'Light CRM' })
    await userEvent.click(within(drawer).getByRole('link', { name: 'Контакти' }))
    expect(router.state.location.pathname).toBe('/contacts')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(sidebar().getByRole('link', { name: 'Контакти' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('UX-02 user menu links to the profile and offers language and sign out', async () => {
    signedInAs(ADMIN_ME)
    const { router } = await renderApp('/')
    await userEvent.click(await screen.findByRole('button', { name: 'Account menu: Ada Admin' }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('menuitemradio', { name: 'English' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(within(menu).getByRole('menuitem', { name: 'Sign out' })).toBeInTheDocument()
    await userEvent.click(within(menu).getByRole('menuitem', { name: 'My profile' }))
    expect(router.state.location.pathname).toBe('/profile')
  })
})
