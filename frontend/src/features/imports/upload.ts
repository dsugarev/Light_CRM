import { ApiError, type Schemas } from '@/api/client'

export type ImportBatch = Schemas['ImportBatchOut']
export type ImportRow = Schemas['ImportRowOut']
export type EntityType = ImportBatch['entity_type']
export const ENTITY_TYPES: readonly EntityType[] = [
  'organizations',
  'contacts',
  'leads',
  'opportunities',
]

/** Upload a file for import (multipart, API spec 15); errors become ApiError. */
export async function uploadImport(entity: EntityType, file: File): Promise<ImportBatch> {
  const form = new FormData()
  form.append('entity_type', entity)
  form.append('file', file)
  const response = await globalThis.fetch(`${globalThis.location.origin}/api/v1/imports`, {
    method: 'POST',
    body: form,
    credentials: 'same-origin',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  })
  const body = (await response.json().catch(() => ({}))) as Record<string, unknown>
  if (!response.ok) throw new ApiError(response.status, body)
  return body as unknown as ImportBatch
}
