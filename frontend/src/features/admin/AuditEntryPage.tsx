import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router'

import { api, call } from '@/api/client'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { useSectionCrumbs } from '@/components/useSectionCrumbs'

import { AuditEntryDetails } from './AuditEntryDetails'
import { useAuditLabels } from './auditLabels'

/** FR-ADM-03: one entry on its own page (a shareable link; the list opens it in a drawer). */
export function AuditEntryPage() {
  const { entryId = '' } = useParams()
  const crumbs = useSectionCrumbs()
  const labels = useAuditLabels()
  const entry = useQuery({
    queryKey: ['audit-log', 'entry', entryId],
    queryFn: () =>
      call(api.GET('/api/v1/audit-log/{entry_id}', { params: { path: { entry_id: entryId } } })),
  })
  if (entry.isError) return <ErrorState error={entry.error} />
  if (!entry.data) return <Loading />
  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader title={labels.action(entry.data.action)} breadcrumbs={[crumbs.auditLog]} />
      <AuditEntryDetails entry={entry.data} />
    </section>
  )
}
