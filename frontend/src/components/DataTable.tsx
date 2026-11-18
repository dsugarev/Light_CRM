import type { ReactNode } from 'react'

import { EmptyState } from '@/components/EmptyState'
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
  sort: string
  onSort: (sort: string) => void
  empty?: ReactNode
  caption?: string
}

function sortState(active: boolean, descending: boolean): 'ascending' | 'descending' | 'none' {
  if (!active) return 'none'
  return descending ? 'descending' : 'ascending'
}

/** Table with keyboard-accessible sortable headers (aria-sort) and an empty state. */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  sort,
  onSort,
  empty,
  caption,
}: DataTableProps<T>) {
  const descending = sort.startsWith('-')
  const active = sort.replace(/^-/, '')
  return (
    <Table>
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
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={columns.length}>
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
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}
