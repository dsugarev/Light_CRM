import { formatDate, formatDateTime, formatMoney, formatMoneyCompact, formatNumber } from './format'

describe('FR-I18N-03 locale formatting in Europe/Sofia time', () => {
  it('shows UTC timestamps in Sofia time', () => {
    expect(formatDateTime('2026-11-17T09:15:00Z', 'en')).toBe('17 Nov 2026, 11:15')
    expect(formatDateTime('2026-07-01T21:30:00Z', 'en')).toBe('2 Jul 2026, 00:30')
    expect(formatDate('2026-11-17T23:30:00Z', 'en')).toBe('18 Nov 2026')
  })

  it('formats numbers and EUR amounts per language', () => {
    expect(formatNumber(1234567.5, 'en')).toBe('1,234,567.5')
    expect(formatNumber(1234567.5, 'bg')).toMatch(/^1\s234\s567,5$/)
    expect(formatMoney('48000.00', 'en')).toBe('€48,000.00')
    expect(formatMoney('48000.00', 'bg')).toMatch(/^48\s000,00\s€$/)
  })
})

describe('UX-13 compact money for chart axes', () => {
  it.each([
    [1_265_236_578, 'en', '€1.3bn'],
    [340_000_000, 'en', '€340m'],
    [0, 'en', '€0'],
    [340_000_000, 'bg', '340 млн. €'],
    [1_265_236_578, 'bg', '1,3 млрд. €'],
  ] as const)('UX-13 %d in %s is %s', (amount, locale, expected) => {
    expect(formatMoneyCompact(amount, locale).replace(/\s/g, ' ')).toBe(expected)
  })
})
