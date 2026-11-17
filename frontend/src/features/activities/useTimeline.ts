import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api, call } from '@/api/client'

import type { RecordRef } from './activityValues'

/** FR-ACT-03: one page of a record's timeline, newest first. */
export function useTimeline(record: RecordRef, page: number, pageSize: number) {
  const query = { page, page_size: pageSize }
  return useQuery({
    queryKey: ['timeline', record.kind, record.id, page, pageSize],
    placeholderData: keepPreviousData,
    queryFn: () => {
      switch (record.kind) {
        case 'lead':
          return call(
            api.GET('/api/v1/leads/{lead_id}/timeline', {
              params: { path: { lead_id: record.id }, query },
            }),
          )
        case 'opportunity':
          return call(
            api.GET('/api/v1/opportunities/{opp_id}/timeline', {
              params: { path: { opp_id: record.id }, query },
            }),
          )
        case 'organization':
          return call(
            api.GET('/api/v1/organizations/{org_id}/timeline', {
              params: { path: { org_id: record.id }, query },
            }),
          )
        case 'contact':
          return call(
            api.GET('/api/v1/contacts/{contact_id}/timeline', {
              params: { path: { contact_id: record.id }, query },
            }),
          )
      }
    },
  })
}
