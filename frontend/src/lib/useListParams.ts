import { useSearchParams } from 'react-router'

/**
 * List state in the URL (CLAUDE.md conventions): page, sort, free text and
 * filters, so a view can be bookmarked and shared. Changing anything but the
 * page returns to page 1.
 */
export function useListParams<F extends string>(defaults: { sort: string; filters: readonly F[] }) {
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)
  const sort = params.get('sort') ?? defaults.sort
  const q = params.get('q') ?? ''
  const archived = params.get('archived') === '1'
  const filters = Object.fromEntries(
    defaults.filters.map((name) => [name, params.getAll(name)]),
  ) as Record<F, string[]>

  const update = (
    changes: Partial<Record<F | 'q' | 'sort' | 'page' | 'archived', string | string[] | null>>,
  ) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes) as [string, string | string[] | null][]) {
      next.delete(key)
      for (const v of Array.isArray(value) ? value : value ? [value] : []) next.append(key, v)
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next, { replace: true })
  }

  /** Query parameters for the API call (filters with values only). */
  const apiQuery = {
    page,
    sort,
    ...(q ? { q } : {}),
    ...(archived ? { include_archived: true } : {}),
    ...Object.fromEntries(Object.entries(filters).filter(([, v]) => (v as string[]).length > 0)),
  }

  /** Whether search, a filter or "show archived" narrows the list (an empty list means less). */
  const filtered =
    q !== '' || archived || Object.values(filters).some((v) => (v as string[]).length > 0)

  /** Remove search and filters, keeping the sort (empty-state "Clear filters"). */
  const clear = () => {
    const next = new URLSearchParams()
    if (params.has('sort')) next.set('sort', sort)
    setParams(next, { replace: true })
  }

  return {
    page,
    sort,
    q,
    archived,
    filters,
    filtered,
    update,
    clear,
    apiQuery,
    key: params.toString(),
  }
}
