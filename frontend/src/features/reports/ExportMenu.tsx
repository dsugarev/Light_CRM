import { useMutation } from '@tanstack/react-query'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useNotify } from '@/lib/notify'
import { useCan } from '@/lib/permissions'

import { download, exportQuery, type ExportFormat } from './download'

const FORMATS: readonly ExportFormat[] = ['xlsx', 'csv']

interface ExportMenuProps {
  /** Export endpoint, e.g. `/api/v1/leads/export`. */
  path: string
  /** The list's current query (filters, sort, search); paging is dropped. */
  query: Record<string, string | number | boolean | readonly string[] | undefined>
}

/**
 * FR-REP-02: download the current list view as XLSX or CSV, filters applied. Hidden for
 * roles without `data.export` (Viewers); a Sales Rep is told the file holds only their own
 * records, as the server applies (requirements section 4, API spec 14).
 */
export function ExportMenu({ path, query }: ExportMenuProps) {
  const { t } = useTranslation('reports')
  const notify = useNotify()
  const can = useCan()
  const noteId = useId()
  const run = useMutation({
    mutationFn: (format: ExportFormat) => download(path, exportQuery(query, format)),
    onError: (error) => {
      notify.error(error)
    },
  })
  if (!can('data.export')) return null
  const ownOnly = !can('records.edit_any')
  return (
    <div
      className="flex items-center gap-1"
      role="group"
      aria-label={t('export.label')}
      aria-describedby={ownOnly ? noteId : undefined}
    >
      {ownOnly ? (
        <span id={noteId} className="mr-1 text-xs text-muted-foreground">
          {t('export.ownOnly')}
        </span>
      ) : null}
      {FORMATS.map((format) => (
        <Button
          key={format}
          type="button"
          size="sm"
          variant="outline"
          disabled={run.isPending}
          onClick={() => {
            run.mutate(format)
          }}
        >
          {t(`export.${format}`)}
        </Button>
      ))}
    </div>
  )
}
