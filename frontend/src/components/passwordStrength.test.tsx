import { render, screen } from '@testing-library/react'

import { PasswordChecklist } from '@/components/PasswordChecklist'
import { passwordStrength } from '@/components/passwordPolicy'

// ASVS 2.1.8: a password strength meter helps people choose a stronger password.

describe('ASVS 2.1.8 password strength', () => {
  it.each([
    ['', 0],
    ['short1!', 1],
    ['aaaaaaaaaaaaaaaa', 1],
    ['correcthorsebat', 1],
    ['Correct-horse-1', 2],
    ['correct horse battery', 3],
    ['Correct horse battery 7', 4],
    ['Пролет в Пловдив 2027', 4],
  ])('ASVS 2.1.8 "%s" rates %i', (password, expected) => {
    expect(passwordStrength(password)).toBe(expected)
  })

  it('ASVS 2.1.8 the checklist shows the meter with a text label once typing starts', () => {
    const { rerender } = render(<PasswordChecklist password="" confirm="" />)
    expect(screen.queryByTestId('password-strength')).not.toBeInTheDocument()
    rerender(<PasswordChecklist password="Correct horse battery 7" confirm="" />)
    expect(screen.getByTestId('password-strength')).toHaveTextContent('Strength: strong')
    rerender(<PasswordChecklist password="short" confirm="" />)
    expect(screen.getByTestId('password-strength')).toHaveTextContent('Strength: weak')
  })
})
