import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ORG, page, referenceLists, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

import { FormField } from './FormField'
import { Input } from './ui/input'

// UX-11: forms build their fields with FormField only.
const sources = import.meta.glob<string>(['/src/features/**/*.tsx', '!/src/**/*.test.tsx'], {
  query: '?raw',
  import: 'default',
  eager: true,
})

describe('UX-11 form conventions', () => {
  it('UX-11 marks a required field without changing its label', () => {
    render(
      <FormField label="Name" required error="validation.required">
        {(control) => <Input {...control} />}
      </FormField>,
    )
    const input = screen.getByLabelText('Name')
    expect(input).toHaveAttribute('aria-required', 'true')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription('Required.')
    expect(screen.getByText('*')).toHaveAttribute('aria-hidden', 'true')
  })

  it('UX-11 leaves optional fields unmarked', () => {
    render(<FormField label="Notes">{(control) => <Input {...control} />}</FormField>)
    expect(screen.getByLabelText('Notes')).not.toHaveAttribute('aria-required')
    expect(screen.queryByText('*')).not.toBeInTheDocument()
  })

  it('UX-11 no feature builds its own labels', () => {
    const offenders = Object.entries(sources)
      .filter(([, text]) => text.includes("from '@/components/ui/label'"))
      .map(([file]) => file)
    expect(offenders).toEqual([])
  })
})

describe('UX-11 unsaved changes', () => {
  beforeEach(() => {
    signedInAs(REP_ME)
    referenceLists()
    server.use(
      http.get('*/api/v1/organizations/duplicate-check', () => HttpResponse.json({ matches: [] })),
      http.get('*/api/v1/contacts', () => HttpResponse.json(page([]))),
      http.get('*/api/v1/organizations', () => HttpResponse.json(page([ORG]))),
    )
  })

  it('UX-11 marks required fields on a record form', async () => {
    await renderApp('/organizations/new')
    expect(await screen.findByLabelText('Name')).toHaveAttribute('aria-required', 'true')
    expect(screen.getByLabelText('City')).not.toHaveAttribute('aria-required')
  })

  it('UX-11 warns before leaving a form with changes, and can stay', async () => {
    const { router } = await renderApp('/organizations/new')
    await userEvent.type(await screen.findByLabelText('Name'), 'Незапазена ООД')
    const nav = screen.getByRole('navigation', { name: 'Main navigation' })
    await userEvent.click(within(nav).getByRole('link', { name: 'Contacts' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Leave without saving?' })
    await userEvent.click(within(dialog).getByRole('button', { name: 'Stay on this page' }))
    await waitFor(() => {
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    })
    expect(router.state.location.pathname).toBe('/organizations/new')
    expect(screen.getByLabelText('Name')).toHaveValue('Незапазена ООД')
  })

  it('UX-11 leaves without saving when asked to', async () => {
    const { router } = await renderApp('/organizations/new')
    await userEvent.type(await screen.findByLabelText('Name'), 'Draft')
    const nav = screen.getByRole('navigation', { name: 'Main navigation' })
    await userEvent.click(within(nav).getByRole('link', { name: 'Contacts' }))
    const dialog = await screen.findByRole('alertdialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Leave without saving' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/contacts')
    })
  })

  it('UX-11 an untouched form does not ask', async () => {
    const { router } = await renderApp('/organizations/new')
    await screen.findByLabelText('Name')
    const nav = screen.getByRole('navigation', { name: 'Main navigation' })
    await userEvent.click(within(nav).getByRole('link', { name: 'Contacts' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/contacts')
    })
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('UX-11 also asks the browser before closing the tab', async () => {
    await renderApp('/organizations/new')
    await userEvent.type(await screen.findByLabelText('Name'), 'Draft')
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })
})
