import { ApiError } from '@/api/client'

export type ExportFormat = 'xlsx' | 'csv'
type QueryValue = string | number | boolean | readonly string[] | undefined

/** Query string for an export: the list's filters and sort, without paging (API spec 14). */
export function exportQuery(query: Record<string, QueryValue>, format: ExportFormat): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (key === 'page' || key === 'page_size' || value === undefined) continue
    for (const v of Array.isArray(value) ? value : [value]) params.append(key, String(v))
  }
  params.set('format', format)
  return params.toString()
}

function filename(response: Response, fallback: string): string {
  const header = response.headers.get('Content-Disposition') ?? ''
  return /filename="([^"]+)"/.exec(header)?.[1] ?? fallback
}

/**
 * Download an export through the session cookie and save it as a file. Errors
 * (for example `export.too_many_rows`) come back as problem details and are thrown.
 */
export async function download(path: string, query: string): Promise<void> {
  const response = await globalThis.fetch(`${globalThis.location.origin}${path}?${query}`, {
    credentials: 'same-origin',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  })
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as Record<string, unknown>
    throw new ApiError(response.status, problem)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename(response, 'export')
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
