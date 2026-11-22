/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { contrast, over, token, WHITE } from '@/test/themeContrast'

// Loop 3 (owner request: warm color scheme). The light theme uses warm neutrals and a
// terracotta brand, and every pair the interface draws keeps WCAG contrast (NFR-10).

const themeCss = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')
const root = /:root\s*\{([^}]*)\}/.exec(themeCss)?.[1] ?? ''

/** Lightness, chroma and hue of a `:root` token written as oklch(). */
function lch(name: string): [number, number, number] {
  const match = new RegExp(`--${name}:\\s*oklch\\(([\\d.]+) ([\\d.]+) ([\\d.]+)\\)`).exec(root)
  if (!match) throw new Error(`token --${name} not found as oklch() in :root`)
  return [Number(match[1]), Number(match[2]), Number(match[3])]
}

describe('UX-01 warm theme (loop 3)', () => {
  it.each([
    'background',
    'foreground',
    'secondary',
    'muted',
    'muted-foreground',
    'accent',
    'border',
    'input',
    'sidebar',
  ])('UX-01 neutral token --%s is tinted warm, not pure grey', (name) => {
    const [, chroma, hue] = lch(name)
    expect(chroma).toBeGreaterThan(0)
    expect(hue).toBeGreaterThanOrEqual(30)
    expect(hue).toBeLessThanOrEqual(80)
  })

  it('UX-01 the brand is a warm terracotta and primary follows it', () => {
    const [, chroma, hue] = lch('brand')
    expect(chroma).toBeGreaterThan(0.1)
    expect(hue).toBeGreaterThanOrEqual(25)
    expect(hue).toBeLessThanOrEqual(55)
    expect(root).toMatch(/--primary:\s*var\(--brand\)/)
  })

  it('UX-01 warning is kept apart from the brand hue, so it does not read as a brand accent', () => {
    expect(Math.abs(lch('warning')[2] - lch('brand')[2])).toBeGreaterThanOrEqual(15)
  })
})

describe('NFR-10 warm theme contrast (loop 3)', () => {
  it.each([
    ['foreground', 'background'],
    ['foreground', 'card'],
    ['muted-foreground', 'background'],
    ['muted-foreground', 'card'],
    ['muted-foreground', 'muted'],
    ['muted-foreground', 'sidebar'],
    ['secondary-foreground', 'secondary'],
    ['accent-foreground', 'accent'],
    ['sidebar-foreground', 'sidebar'],
    ['sidebar-accent-foreground', 'sidebar-accent'],
    ['primary-foreground', 'primary'],
    ['primary-foreground', 'primary-hover'],
    ['primary', 'background'],
    ['primary', 'card'],
  ])('NFR-10 text in --%s on --%s keeps 4.5:1', (text, surface) => {
    expect(contrast(token(text), token(surface))).toBeGreaterThanOrEqual(4.5)
  })

  it('NFR-10 muted text on a table header (muted at 70% over the card) keeps 4.5:1', () => {
    const header = over(token('muted'), 0.7, token('card'))
    expect(contrast(token('muted-foreground'), header)).toBeGreaterThanOrEqual(4.5)
  })

  it('NFR-10 accent text on a 60% accent hover keeps 4.5:1', () => {
    const hover = over(token('sidebar-accent'), 0.6, token('sidebar'))
    expect(contrast(token('sidebar-foreground'), hover)).toBeGreaterThanOrEqual(4.5)
  })

  it.each(['background', 'card', 'sidebar'])(
    'NFR-10 the focus ring keeps 3:1 against --%s (WCAG 1.4.11)',
    (surface) => {
      expect(contrast(token('ring'), token(surface))).toBeGreaterThanOrEqual(3)
    },
  )

  it.each(['chart-2', 'chart-5'])(
    'NFR-10 dashboard series --%s keeps 3:1 against the card (WCAG 1.4.11)',
    (series) => {
      expect(contrast(token(series), WHITE)).toBeGreaterThanOrEqual(3)
    },
  )
})
