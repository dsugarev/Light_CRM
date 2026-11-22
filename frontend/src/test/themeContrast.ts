// Shared by the theme contrast tests (loops 2 and 3, NFR-10 / WCAG 1.4.3 and 1.4.11).
/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Read from disk: Vitest's CSS handling empties every `?raw` import of a stylesheet.
// Vitest runs from frontend/, so the path is relative to it.
const themeCss = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')

export type Rgb = [number, number, number]

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
export function over(fg: Rgb, alpha: number, bg: Rgb): Rgb {
  return fg.map((c, i) => decode(encode(c) * alpha + encode(bg[i] ?? 0) * (1 - alpha))) as Rgb
}

export function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * The light-theme (`:root`) value of a token, parsed from src/index.css. A token defined as
 * `var(--other)` resolves to that token.
 */
export function token(name: string): Rgb {
  const root = /:root\s*\{([^}]*)\}/.exec(themeCss)?.[1] ?? ''
  const alias = new RegExp(`--${name}:\\s*var\\(--([\\w-]+)\\)`).exec(root)
  if (alias?.[1]) return token(alias[1])
  const match = new RegExp(`--${name}:\\s*oklch\\(([\\d.]+) ([\\d.]+) ([\\d.]+)\\)`).exec(root)
  if (!match) throw new Error(`token --${name} not found as oklch() in :root`)
  return oklchToLinear(Number(match[1]), Number(match[2]), Number(match[3]))
}

export const WHITE: Rgb = [1, 1, 1]
