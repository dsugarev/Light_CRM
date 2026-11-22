import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { EmptyState } from '@/components/EmptyState'
import { RowActions, type RowAction } from '@/components/RowActions'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export interface Column<T> {
  key: string
  header: string
  /** API sort field; omitted when the column cannot be sorted. */
  sortKey?: string
  cell: (row: T) => ReactNode
  className?: string
}

interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  /** Current sort, as in the URL and the API: `field` or `-field` (descending). */
  sort: string
  onSort: (sort: string) => void
  /** Shown instead of rows when there are none; a string becomes the EmptyState message. */
  empty?: ReactNode
  /** Screen-reader name of the table. */
  caption?: string
  /** UX-08: a "…" menu at the end of each row; `rowLabel` names the row in its label. */
  rowActions?: ((row: T) => RowAction[]) | undefined
  rowLabel?: ((row: T) => string) | undefined
  /**
   * Loop 2: the rows shown are the previous result while a new page, sort or filter loads
   * (TanStack Query `isPlaceholderData`). The table is marked busy, the rows dim and a thin
   * bar moves above them, all after 200 ms so quick answers do not flicker.
   */
  busy?: boolean | undefined
}

function sortState(active: boolean, descending: boolean): 'ascending' | 'descending' | 'none' {
  if (!active) return 'none'
  return descending ? 'descending' : 'ascending'
}

/**
 * The shared list table (UX-08): keyboard-accessible sortable headers (`aria-sort`), an
 * empty state, and optional per-row action menus. It holds no state: keep page, sort and
 * filters in the URL with `useListParams` and pass them in, so views can be shared.
 *
 * ```tsx
 * const list = useListParams({ sort: 'name', filters: ['status'] as const })
 * const columns: Column<Thing>[] = [
 *   { key: 'name', header: t('name'), sortKey: 'name', cell: (row) => row.name },
 *   { key: 'status', header: t('status'), cell: (row) => <StatusBadge status={row.status} /> },
 * ]
 * <DataTable
 *   caption={t('title')}
 *   columns={columns}
 *   rows={data.items}
 *   rowKey={(row) => row.id}
 *   sort={list.sort}
 *   onSort={(sort) => { list.update({ sort }) }}
 *   rowLabel={(row) => row.name}
 *   rowActions={(row) => [{ label: t('open'), to: `/things/${row.id}` }]}
 * />
 * <Pagination page={list.page} pageSize={25} total={data.total} onPageChange={...} />
 * ```
 *
 * `sortKey` must be a sort field the list endpoint accepts (API spec 1.3).
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  sort,
  onSort,
  empty,
  caption,
  rowActions,
  rowLabel,
  busy = false,
}: DataTableProps<T>) {
  const { t } = useTranslation()
  const span = columns.length + (rowActions ? 1 : 0)
  const descending = sort.startsWith('-')
  const active = sort.replace(/^-/, '')
  return (
    <div className="relative">
      {busy ? (
        <div
          data-testid="table-busy"
          aria-hidden="true"
          className="busy-track absolute inset-x-0 top-0 z-10 h-0.5 overflow-hidden rounded-full bg-info/15"
        >
          <div className="busy-bar h-full w-2/5 rounded-full bg-info" />
        </div>
      ) : null}
      <Table aria-busy={busy || undefined}>
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <TableHeader>
          <TableRow>
            {columns.map((column) => {
              const isActive = column.sortKey !== undefined && column.sortKey === active
              const ariaSort = sortState(isActive, descending)
              return (
                <TableHead
                  key={column.key}
                  className={column.className}
                  aria-sort={column.sortKey ? ariaSort : undefined}
                >
                  {column.sortKey ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-medium hover:underline"
                      onClick={() => {
                        const key = column.sortKey ?? ''
                        onSort(isActive && !descending ? `-${key}` : key)
                      }}
                    >
                      {column.header}
                      <span aria-hidden="true" className="text-muted-foreground">
                        {isActive ? (descending ? '↓' : '↑') : '↕'}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </TableHead>
              )
            })}
            {rowActions ? (
              <TableHead className="w-12">
                <span className="sr-only">{t('table.actions')}</span>
              </TableHead>
            ) : null}
          </TableRow>
        </TableHeader>
        <TableBody
          data-busy={busy || undefined}
          className="transition-opacity duration-200 data-busy:opacity-60 data-busy:delay-200"
        >
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={span}>
                {typeof empty === 'string' || empty === undefined ? (
                  <EmptyState message={empty} />
                ) : (
                  empty
                )}
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => (
              <TableRow key={rowKey(row)}>
                {columns.map((column) => (
                  <TableCell key={column.key} className={column.className}>
                    {column.cell(row)}
                  </TableCell>
                ))}
                {rowActions ? (
                  <TableCell className="w-12 text-right">
                    <RowActions name={rowLabel?.(row) ?? rowKey(row)} actions={rowActions(row)} />
                  </TableCell>
                ) : null}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
