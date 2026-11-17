import { useQuery } from '@tanstack/react-query'

import { api, call, type Schemas } from '@/api/client'
import type { Locale } from '@/i18n'

export type ReferenceItem = Schemas['ReferenceItem']

export const REFERENCE_LISTS = [
  'industries',
  'lead-sources',
  'disqualification-reasons',
  'loss-reasons',
  'external-systems',
] as const
export type ReferenceListName = (typeof REFERENCE_LISTS)[number]

export function useReferenceList(list: ReferenceListName, includeInactive = false) {
  return useQuery({
    queryKey: ['reference', list, includeInactive],
    queryFn: () =>
      call(
        api.GET('/api/v1/reference/{list}', {
          params: { path: { list }, query: { include_inactive: includeInactive } },
        }),
      ),
    staleTime: 5 * 60_000,
  })
}

/** Reference values carry both names; show the one for the UI language. */
export function referenceName(item: { name_en: string; name_bg: string }, locale: Locale): string {
  return locale === 'bg' ? item.name_bg : item.name_en
}
