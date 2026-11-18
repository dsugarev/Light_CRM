import type { Locale } from '@/i18n'

// FR-I18N-03: stored in UTC, shown in Europe/Sofia, formatted per language.
export const DISPLAY_TIME_ZONE = 'Europe/Sofia'
const TAGS: Record<Locale, string> = { en: 'en-GB', bg: 'bg-BG' }

export function formatDateTime(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(TAGS[locale], {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: DISPLAY_TIME_ZONE,
  }).format(new Date(iso))
}

export function formatDate(iso: string, locale: Locale): string {
  return new Intl.DateTimeFormat(TAGS[locale], {
    dateStyle: 'medium',
    timeZone: DISPLAY_TIME_ZONE,
  }).format(new Date(iso))
}

export function formatNumber(value: number, locale: Locale): string {
  return new Intl.NumberFormat(TAGS[locale]).format(value)
}

/** Money arrives as a decimal string (API spec 1.1); EUR only in R1. */
export function formatMoney(amount: string, locale: Locale, currency = 'EUR'): string {
  return new Intl.NumberFormat(TAGS[locale], { style: 'currency', currency }).format(Number(amount))
}

/**
 * A calendar date without a time (`YYYY-MM-DD`, e.g. an expected close date),
 * formatted as is: no time-zone shift applies to a day.
 */
export function formatDay(day: string, locale: Locale): string {
  return new Intl.DateTimeFormat(TAGS[locale], { dateStyle: 'medium', timeZone: 'UTC' }).format(
    new Date(`${day}T00:00:00Z`),
  )
}

/** A share between 0 and 1 as a percentage, e.g. 0.4 → "40%". */
export function formatPercent(share: number, locale: Locale): string {
  return new Intl.NumberFormat(TAGS[locale], { style: 'percent', maximumFractionDigits: 1 }).format(
    share,
  )
}

const RELATIVE_STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.35],
  ['month', 12],
  ['year', Number.POSITIVE_INFINITY],
]

/** How long ago (or until) `iso` is from `now`, in words: "3 hours ago", "преди 2 дни". */
export function formatRelative(iso: string, now: number, locale: Locale): string {
  let value = (new Date(iso).getTime() - now) / 1000
  for (const [unit, size] of RELATIVE_STEPS) {
    if (Math.abs(value) < size) {
      return new Intl.RelativeTimeFormat(TAGS[locale], { numeric: 'auto' }).format(
        Math.round(value),
        unit,
      )
    }
    value /= size
  }
  return formatDateTime(iso, locale)
}
