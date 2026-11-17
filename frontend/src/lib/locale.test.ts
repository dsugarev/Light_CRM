import { detectLocale, storeLocale } from './locale'

describe('FR-I18N-01 locale detection', () => {
  it('uses a stored choice first', () => {
    expect(detectLocale('bg', ['en-US'])).toBe('bg')
  })

  it('follows the browser language when nothing is stored', () => {
    expect(detectLocale(null, ['bg-BG', 'en'])).toBe('bg')
    expect(detectLocale(null, ['de-DE', 'en-GB'])).toBe('en')
  })

  it('ignores unsupported stored values', () => {
    expect(detectLocale('fr', ['bg'])).toBe('bg')
  })

  it('remembers the chosen language', () => {
    storeLocale('bg')
    expect(detectLocale(undefined, ['en'])).toBe('bg')
  })
})
