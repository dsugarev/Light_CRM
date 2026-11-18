import { describe, expect, it } from 'vitest'

// UX-01: every color comes from the theme tokens in src/index.css. Component and
// module files may not carry color literals or Tailwind palette colors.
const sources = import.meta.glob<string>(
  ['/src/**/*.{ts,tsx}', '!/src/**/*.test.{ts,tsx}', '!/src/test/**', '!/src/api/schema.d.ts'],
  { query: '?raw', import: 'default', eager: true },
)

const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\(/
const PALETTE =
  /\b(?:text|bg|border|ring|fill|stroke|from|via|to|outline|decoration|divide|shadow|accent|caret)-(?:white|black|(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3})\b/

function offenders(pattern: RegExp): string[] {
  return Object.entries(sources).flatMap(([file, text]) =>
    text
      .split('\n')
      .map((line, index) => ({ line, number: index + 1 }))
      .filter(({ line }) => pattern.test(line))
      .map(({ line, number }) => `${file}:${String(number)}: ${line.trim()}`),
  )
}

describe('UX-01 design tokens', () => {
  it('scans the source files', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(50)
  })

  it('UX-01 has no hex, rgb, hsl or oklch color literals outside the theme file', () => {
    expect(offenders(COLOR_LITERAL)).toEqual([])
  })

  it('UX-01 uses theme color utilities, not Tailwind palette colors', () => {
    expect(offenders(PALETTE)).toEqual([])
  })
})
