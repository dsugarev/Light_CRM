import { useSearchParams } from 'react-router'

/**
 * Owner and period of a report, kept in the URL (list state convention):
 * `owner=me` or everyone, and a calendar year (default: the current one).
 */
export function useReportScope() {
  const [params, setParams] = useSearchParams()
  const currentYear = new Date().getFullYear()
  const year = Number(params.get('year') ?? currentYear) || currentYear
  const mine = params.get('owner') === 'me'
  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) next.delete(key)
      else next.set(key, value)
    }
    setParams(next, { replace: true })
  }
  const query = {
    from: `${String(year)}-01-01`,
    to: `${String(year)}-12-31`,
    ...(mine ? { owner_id: 'me' } : {}),
  }
  return { year, mine, years: [currentYear, currentYear - 1, currentYear - 2], update, query }
}
