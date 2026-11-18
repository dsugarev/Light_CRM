import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { ADMIN_ME, CONTACT, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

// FR-ADM-04: an Admin exports a contact's personal data or anonymizes the contact.

function onContact(contact = CONTACT) {
  server.use(http.get(`*/api/v1/contacts/${contact.id}`, () => HttpResponse.json(contact)))
}

describe('FR-ADM-04 GDPR tools', () => {
  it('downloads the personal data as a JSON file', async () => {
    signedInAs(ADMIN_ME)
    onContact()
    let exported = false
    server.use(
      http.get(`*/api/v1/contacts/${CONTACT.id}/personal-data`, () => {
        exported = true
        return HttpResponse.json({ contact: CONTACT })
      }),
    )
    const createObjectURL = vi.fn(() => 'blob:personal-data')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    await renderApp(`/contacts/${CONTACT.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Export personal data' }))
    await waitFor(() => {
      expect(click).toHaveBeenCalled()
    })
    expect(exported).toBe(true)
    expect(createObjectURL).toHaveBeenCalled()
    const anchor = click.mock.contexts[0] as HTMLAnchorElement
    expect(anchor.download).toBe(`contact-${CONTACT.id}-personal-data.json`)
    click.mockRestore()
  })

  it('anonymizes only after the word is typed', async () => {
    signedInAs(ADMIN_ME)
    let current = CONTACT
    let body: unknown = null
    server.use(
      http.get(`*/api/v1/contacts/${CONTACT.id}`, () => HttpResponse.json(current)),
      http.post(`*/api/v1/contacts/${CONTACT.id}/anonymize`, async ({ request }) => {
        body = await request.json()
        current = {
          ...CONTACT,
          first_name: 'Anonymized',
          last_name: '#0000c1',
          full_name: 'Anonymized #0000c1',
          email: null,
          phone: null,
          job_title: null,
          anonymized_at: '2026-11-18T10:00:00Z',
        }
        return HttpResponse.json(current)
      }),
    )
    await renderApp(`/contacts/${CONTACT.id}`)
    const form = await screen.findByRole('form', { name: 'Anonymize contact' })
    const button = within(form).getByRole('button', { name: 'Anonymize contact' })
    expect(button).toBeDisabled()
    await userEvent.type(within(form).getByLabelText('Type ANONYMIZE to confirm'), 'anonymize')
    expect(button).toBeDisabled()
    await userEvent.clear(within(form).getByLabelText('Type ANONYMIZE to confirm'))
    await userEvent.type(within(form).getByLabelText('Type ANONYMIZE to confirm'), 'ANONYMIZE')
    await userEvent.click(button)

    expect(await screen.findByRole('heading', { name: 'Anonymized #0000c1' })).toBeInTheDocument()
    expect(body).toEqual({ confirm: 'ANONYMIZE' })
    expect(screen.getByText(/^Anonymized on /)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Anonymize contact' })).not.toBeInTheDocument()
  })

  it('is not offered to other roles', async () => {
    signedInAs(REP_ME)
    onContact()
    await renderApp(`/contacts/${CONTACT.id}`)
    expect(await screen.findByRole('heading', { name: CONTACT.full_name })).toBeInTheDocument()
    expect(screen.queryByText('Personal data (GDPR)')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Export personal data' })).not.toBeInTheDocument()
  })
})
