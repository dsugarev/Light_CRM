import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { PasswordChecklist } from '@/components/PasswordChecklist'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

function rule(name: RegExp): HTMLElement {
  const text = within(screen.getByRole('list', { name: 'Password rules' })).getByText(name)
  return text.closest('li') ?? text
}

describe('UX-07 password checklist', () => {
  it.each([
    ['a', /At least 12 characters/, '(not yet)'],
    ['twelve-chars', /At least 12 characters/, '(done)'],
    ['x'.repeat(129), /At most 128 characters/, '(not yet)'],
    ['x'.repeat(128), /At most 128 characters/, '(done)'],
  ])('UX-07 length rule for %#', (password, name, state) => {
    render(<PasswordChecklist password={password} confirm="" />)
    expect(rule(name)).toHaveTextContent(state)
  })

  it('UX-07 the common-password rule says it is checked on save', () => {
    render(<PasswordChecklist password="password1234" confirm="" />)
    const common = rule(/Not a commonly used password \(checked when you save\)/)
    expect(common).not.toHaveTextContent('(done)')
    expect(common).not.toHaveTextContent('(not yet)')
  })

  it.each([
    ['Winter-Harbour-77', '', '(not yet)'],
    ['Winter-Harbour-77', 'Winter-Harbour-7', '(not yet)'],
    ['Winter-Harbour-77', 'Winter-Harbour-77', '(done)'],
  ])('UX-07 match rule for %s / %s', (password, confirm, state) => {
    render(<PasswordChecklist password={password} confirm={confirm} />)
    expect(rule(/Both entries match/)).toHaveTextContent(state)
  })
})

describe('UX-07 set password page', () => {
  it('UX-07 updates the checklist while typing', async () => {
    server.use(
      http.get('*/api/v1/auth/password/token/:token', () =>
        HttpResponse.json({ email: 'n@example.test', purpose: 'invite' }),
      ),
    )
    await renderApp('/set-password#token=t')
    const password = await screen.findByLabelText('New password')
    await userEvent.type(password, 'Winter-Harbour-77')
    expect(rule(/At least 12 characters/)).toHaveTextContent('(done)')
    expect(rule(/Both entries match/)).toHaveTextContent('(not yet)')
    await userEvent.type(screen.getByLabelText('Repeat the new password'), 'Winter-Harbour-77')
    expect(rule(/Both entries match/)).toHaveTextContent('(done)')
  })

  it('UX-07 explains an expired link and what to do next', async () => {
    server.use(
      http.get('*/api/v1/auth/password/token/:token', () => problem(400, 'auth.token_invalid')),
    )
    await renderApp('/set-password#token=expired')
    expect(
      await screen.findByRole('heading', { name: 'This link can no longer be used' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Request a new link' })).toHaveAttribute(
      'href',
      '/forgot-password',
    )
    expect(screen.getByRole('link', { name: 'Back to sign-in' })).toHaveAttribute(
      'href',
      '/sign-in',
    )
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument()
  })

  it('UX-07 explains an incomplete link, in Bulgarian too', async () => {
    await renderApp('/set-password', 'bg')
    expect(
      await screen.findByRole('heading', { name: 'Тази връзка вече не може да се използва' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Връзката е непълна/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Поискай нова връзка' })).toBeInTheDocument()
  })
})
