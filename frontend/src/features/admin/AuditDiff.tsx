import { useTranslation } from 'react-i18next'

type Plain = Record<string, unknown>

function isPlain(value: unknown): value is Plain {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

const cellClass = 'align-top px-2 py-1.5 whitespace-pre-wrap [overflow-wrap:anywhere]'

/** A value as text: strings as they are, everything else as indented JSON (never as HTML). */
function Value({ value }: { value: unknown }) {
  const { t } = useTranslation('admin')
  if (value === undefined || value === null)
    return <span className="text-muted-foreground">{t('audit.detail.none')}</span>
  if (typeof value === 'string') return <>{value}</>
  if (typeof value === 'number' || typeof value === 'boolean') return <>{String(value)}</>
  return <code className="font-mono text-xs">{JSON.stringify(value, null, 2)}</code>
}

/** Formatted JSON, for values that are not field maps. */
export function AuditJson({ value }: { value: unknown }) {
  const { t } = useTranslation('admin')
  if (value === null || value === undefined)
    return <p className="text-muted-foreground">{t('audit.detail.none')}</p>
  return (
    <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap [overflow-wrap:anywhere]">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

/**
 * UX-10: before and after side by side, one row per field, changed fields highlighted.
 * Falls back to formatted JSON when either side is not a field map.
 */
export function AuditDiff({ before, after }: { before: unknown; after: unknown }) {
  const { t } = useTranslation('admin')
  const comparable =
    (isPlain(before) || before == null) && (isPlain(after) || after == null) && (before ?? after)
  if (!comparable) {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <section aria-label={t('audit.detail.before')}>
          <h3 className="mb-2 text-sm font-medium">{t('audit.detail.before')}</h3>
          <AuditJson value={before} />
        </section>
        <section aria-label={t('audit.detail.after')}>
          <h3 className="mb-2 text-sm font-medium">{t('audit.detail.after')}</h3>
          <AuditJson value={after} />
        </section>
      </div>
    )
  }
  const left: Plain = isPlain(before) ? before : {}
  const right: Plain = isPlain(after) ? after : {}
  const fields = [...new Set([...Object.keys(left), ...Object.keys(right)])].sort()
  return (
    <div className="overflow-x-auto">
      <table className="w-full table-fixed border-collapse text-sm">
        <caption className="sr-only">{t('audit.detail.changes')}</caption>
        <thead>
          <tr className="border-b text-left">
            <th scope="col" className="w-1/4 px-2 py-1.5 font-medium">
              {t('audit.detail.field')}
            </th>
            <th scope="col" className="px-2 py-1.5 font-medium">
              {t('audit.detail.before')}
            </th>
            <th scope="col" className="px-2 py-1.5 font-medium">
              {t('audit.detail.after')}
            </th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => {
            // A missing field and null both mean "no value".
            const changed =
              JSON.stringify(left[field] ?? null) !== JSON.stringify(right[field] ?? null)
            return (
              <tr
                key={field}
                data-changed={changed || undefined}
                className={`border-b ${changed ? 'bg-primary/5' : 'text-muted-foreground'}`}
              >
                <th scope="row" className={`${cellClass} text-left font-mono text-xs font-normal`}>
                  {changed ? (
                    <span
                      aria-hidden="true"
                      className="mr-1 inline-block size-2 rounded-full bg-primary"
                    />
                  ) : null}
                  {field}
                  {changed ? (
                    <>
                      {' '}
                      <span className="sr-only">({t('audit.detail.changed')})</span>
                    </>
                  ) : null}
                </th>
                <td className={cellClass}>
                  <Value value={left[field]} />
                </td>
                <td className={`${cellClass} ${changed ? 'font-medium text-foreground' : ''}`}>
                  <Value value={right[field]} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
