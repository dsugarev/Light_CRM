import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { websiteHref } from '@/lib/url'
import { CONTACT, LEAD, page, REP_ME, referenceLists, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

import { EmailLink, PhoneLink, WebsiteLink } from './ContactLinks'

describe('page titles (WCAG 2.4.2)', () => {
  beforeEach(() => {
    referenceLists()
  })

  it('names the page in the browser tab', async () => {
    signedInAs(REP_ME)
    server.use(http.get('*/api/v1/leads', () => HttpResponse.json(page([LEAD]))))
    await renderApp('/leads')
    await waitFor(() => {
      expect(document.title).toBe('Leads · Light CRM')
    })
  })

  it('uses the record name on a record page', async () => {
    signedInAs(REP_ME)
    server.use(http.get(`*/api/v1/contacts/${CONTACT.id}`, () => HttpResponse.json(CONTACT)))
    await renderApp(`/contacts/${CONTACT.id}`)
    await waitFor(() => {
      expect(document.title).toBe(`${CONTACT.full_name} · Light CRM`)
    })
  })

  it('titles signed-out and error pages, in Bulgarian too', async () => {
    await renderApp('/sign-in', 'bg')
    await waitFor(() => {
      expect(document.title).toBe('Вход · Light CRM')
    })
    await renderApp('/does-not-exist')
    await waitFor(() => {
      expect(document.title).toBe('This page does not exist. · Light CRM')
    })
  })
})

describe('contact details as links', () => {
  it('calls the number without spaces or punctuation', () => {
    render(<PhoneLink phone="+359 (2) 123-45-67" />)
    expect(screen.getByRole('link', { name: '+359 (2) 123-45-67' })).toHaveAttribute(
      'href',
      'tel:+35921234567',
    )
  })

  it('writes an email', () => {
    render(<EmailLink email="maria@example.test" />)
    expect(screen.getByRole('link', { name: 'maria@example.test' })).toHaveAttribute(
      'href',
      'mailto:maria@example.test',
    )
  })

  it('opens a website in a new tab without giving it access to this one', () => {
    render(<WebsiteLink website="acme.example.test" />)
    const link = screen.getByRole('link', { name: 'acme.example.test' })
    expect(link).toHaveAttribute('href', 'https://acme.example.test/')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it.each([
    ['https://acme.example.test/about', 'https://acme.example.test/about'],
    ['http://acme.example.test', 'http://acme.example.test/'],
    ['www.acme.example.test', 'https://www.acme.example.test/'],
    ['javascript:alert(1)', null],
    ['ftp://files.example.test', null],
  ])('only links http(s) addresses: %s', (website, href) => {
    expect(websiteHref(website)).toBe(href)
  })

  it('shows any other address as plain text', () => {
    render(<WebsiteLink website="javascript:alert(1)" />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('javascript:alert(1)')).toBeInTheDocument()
  })

  it('shows nothing when there is no value', () => {
    const { container } = render(<PhoneLink phone={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
