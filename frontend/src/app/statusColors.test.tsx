/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { render, screen } from '@testing-library/react'

import { ImportStatusBadge } from '@/features/imports/ImportStatusBadge'
import { LeadStatusBadge } from '@/features/leads/LeadStatusBadge'
import { StageBadge, StaleBadge } from '@/features/opportunities/StageBadge'

// Read from disk: Vitest's CSS handling empties every `?raw` import of a stylesheet.
// Vitest runs from frontend/, so the path is relative to it.
const themeCss = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')

// UX-01 / NFR-10, loop 2: status colors come from theme tokens and keep text contrast.

type Rgb = [number, number, number]

/** OKLCH to linear sRGB (Björn Ottosson's OKLab matrices), clamped to the gamut. */
function oklchToLinear(l: number, c: number, hDeg: number): Rgb {
  const h = (hDeg * Math.PI) / 180
  const a = c * Math.cos(h)
  const b = c * Math.sin(h)
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3
  const rgb: Rgb = [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ]
  return rgb.map((x) => Math.min(1, Math.max(0, x))) as Rgb
}

const encode = (x: number) => (x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055)
const decode = (x: number) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)
const luminance = ([r, g, b]: Rgb) => 0.2126 * r + 0.7152 * g + 0.0722 * b

/** A color at `alpha` over a background, blended in sRGB as browsers do. */
function over(fg: Rgb, alpha: number, bg: Rgb): Rgb {
  return fg.map((c, i) => decode(encode(c) * alpha + encode(bg[i] ?? 0) * (1 - alpha))) as Rgb
}

function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

/** The light-theme (`:root`) value of a token, parsed from src/index.css. */
function token(name: string): Rgb {
  const root = /:root\s*\{([^}]*)\}/.exec(themeCss)?.[1] ?? ''
  const match = new RegExp(`--${name}:\\s*oklch\\(([\\d.]+) ([\\d.]+) ([\\d.]+)\\)`).exec(root)
  if (!match) throw new Error(`token --${name} not found as oklch() in :root`)
  return oklchToLinear(Number(match[1]), Number(match[2]), Number(match[3]))
}

const WHITE: Rgb = [1, 1, 1]

describe('NFR-10 status color contrast (loop 2)', () => {
  it.each(['success', 'warning', 'info', 'destructive'])(
    'NFR-10 %s text keeps 4.5:1 on white and on its 10% badge tint',
    (name) => {
      const color = token(name)
      expect(contrast(color, WHITE)).toBeGreaterThanOrEqual(4.5)
      expect(contrast(color, over(color, 0.1, WHITE))).toBeGreaterThanOrEqual(4.5)
    },
  )

  it('NFR-10 the contrast helper agrees with a known pair (black on white is 21:1)', () => {
    expect(contrast([0, 0, 0], WHITE)).toBeCloseTo(21, 5)
  })
})

function variantOf(text: string): string {
  const cls = screen.getByText(text).className
  return /\btext-(success|warning|info|destructive)\b/.exec(cls)?.[1] ?? 'neutral'
}

describe('UX-01 status badges use semantic colors (loop 2)', () => {
  it('FR-LEAD-05 lead statuses: new blue, qualified green, disqualified red, others neutral', () => {
    render(
      <>
        <LeadStatusBadge status="new" />
        <LeadStatusBadge status="contacted" />
        <LeadStatusBadge status="qualified" />
        <LeadStatusBadge status="converted" />
        <LeadStatusBadge status="disqualified" />
      </>,
    )
    expect(variantOf('New')).toBe('info')
    expect(variantOf('Contacted')).toBe('neutral')
    expect(variantOf('Qualified')).toBe('success')
    expect(variantOf('Converted')).toBe('neutral')
    expect(variantOf('Disqualified')).toBe('destructive')
  })

  it('FR-OPP-06 stages: open blue, won green, lost red; stale amber', () => {
    const stage = (stage_type: 'open' | 'won' | 'lost', name: string) => ({
      id: name,
      name_en: name,
      name_bg: name,
      stage_type,
      position: 1,
      default_probability: 0,
    })
    render(
      <>
        <StageBadge stage={stage('open', 'Proposal')} />
        <StageBadge stage={stage('won', 'Won')} />
        <StageBadge stage={stage('lost', 'Lost')} />
        <StaleBadge />
      </>,
    )
    expect(variantOf('Proposal')).toBe('info')
    expect(variantOf('Won')).toBe('success')
    expect(variantOf('Lost')).toBe('destructive')
    expect(variantOf('Needs attention')).toBe('warning')
  })

  it('FR-IMP-01 imports: steps in progress blue, imported green, rolled back neutral', () => {
    render(
      <>
        <ImportStatusBadge status="validated" />
        <ImportStatusBadge status="committed" />
        <ImportStatusBadge status="rolled_back" />
      </>,
    )
    expect(variantOf('Checked')).toBe('info')
    expect(variantOf('Imported')).toBe('success')
    expect(variantOf('Rolled back')).toBe('neutral')
  })
})
