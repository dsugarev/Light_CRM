import { screen, within } from '@testing-library/react'

import { ADMIN_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'

// Loop 3: the warm shell. Classes are checked because the look is the requirement; the
// accessible names and roles stay as tested in appShell.test.tsx.

describe('UX-02 warm app shell (loop 3)', () => {
  it('UX-02 the sidebar sits on the warm sidebar surface', async () => {
    signedInAs(ADMIN_ME)
    await renderApp('/')
    await screen.findByRole('navigation', { name: 'Main navigation' })
    expect(document.getElementById('app-sidebar')).toHaveClass('bg-sidebar')
  })

  it('UX-02 the active page is a peach tint with a terracotta edge; others warm on hover', async () => {
    signedInAs(ADMIN_ME)
    await renderApp('/organizations')
    const nav = within(await screen.findByRole('navigation', { name: 'Main navigation' }))
    const active = nav.getByRole('link', { name: 'Organizations' })
    expect(active).toHaveClass('bg-sidebar-accent', 'text-sidebar-accent-foreground')
    expect(active.className).toContain('var(--sidebar-primary)')
    expect(nav.getByRole('link', { name: 'Home' })).toHaveClass('hover:bg-sidebar-accent/60')
  })

  it('UX-01 the header shows a decorative brand mark next to the app name', async () => {
    signedInAs(ADMIN_ME)
    await renderApp('/')
    const mark = await screen.findByTestId('brand-mark')
    expect(mark).toHaveAttribute('aria-hidden', 'true')
    expect(mark).toHaveClass('bg-primary', 'text-primary-foreground')
    expect(mark).toHaveTextContent('L')
    // The link is still named by the app name alone.
    expect(screen.getByRole('link', { name: 'Light CRM' })).toContainElement(mark)
  })

  it('UX-01 primary buttons darken on hover instead of fading (white text keeps contrast)', async () => {
    signedInAs(ADMIN_ME)
    await renderApp('/organizations')
    const create = await screen.findByRole('link', { name: 'New organization' })
    expect(create).toHaveClass('hover:bg-primary-hover')
    expect(create.className).not.toContain('hover:bg-primary/80')
  })
})
