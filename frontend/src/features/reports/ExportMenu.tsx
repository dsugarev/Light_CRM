import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useNotify } from '@/lib/notify'

import { download, exportQuery, type ExportFormat } from './download'

const FORMATS: readonly ExportFormat[] = ['xlsx', 'csv']

interface ExportMenuProps {
  /** Export endpoint, e.g. `/api/v1/leads/export`. */
  path: string
  /** The list's current query (filters, sort, search); paging is dropped. */
  query: Record<string, string | number | boolean | readonly string[] | undefined>
}

/** FR-REP-02: download the current list view as XLSX or CSV, filters applied. */
export function ExportMenu({ path, query }: ExportMenuProps) {
  const { t } = useTranslation('reports')
  const notify = useNotify()
  const run = useMutation({
    mutationFn: (format: ExportFormat) => download(path, exportQuery(query, format)),
    onError: (error) => {
      notify.error(error)
    },
  })
  return (
    <div className="flex items-center gap-1" role="group" aria-label={t('export.label')}>
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
