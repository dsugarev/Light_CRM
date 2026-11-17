import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { Schemas } from '@/api/client'
import { ADMIN_ME, page, REP_ME, signedInAs } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const MANAGER_ME: Schemas['Me'] = {
  ...REP_ME,
  role: 'sales_manager',
  permissions: [...REP_ME.permissions, 'records.edit_any', 'data.import'],
}

const BATCH: Schemas['ImportBatchOut'] = {
  id: '01930000-0000-7000-8000-0000000009b1',
  entity_type: 'organizations',
  file_name: 'orgs.xlsx',
  status: 'uploaded',
  columns: ['Име', 'Град', 'Бележка'],
  mapping: { Име: 'name', Град: 'city', Бележка: null },
  duplicate_mode: null,
  fields: [
    { key: 'name', name_en: 'Name', name_bg: 'Име', required: true },
    { key: 'city', name_en: 'City', name_bg: 'Град', required: false },
    { key: 'notes', name_en: 'Notes', name_bg: 'Бележки', required: false },
  ],
  counts: { rows: 3, valid: 0, invalid: 0, duplicate: 0, created: 0, updated: 0, skipped: 0 },
  created_by: { id: MANAGER_ME.id, full_name: MANAGER_ME.full_name },
  created_at: '2026-11-17T09:00:00Z',
  committed_at: null,
  rolled_back_at: null,
  expires_at: '2026-11-24T09:00:00Z',
}

const VALIDATED: Schemas['ImportBatchOut'] = {
  ...BATCH,
  status: 'validated',
  duplicate_mode: 'skip',
  counts: { ...BATCH.counts, valid: 1, invalid: 1, duplicate: 1 },
}

function onBatch(batch: Schemas['ImportBatchOut'], rows: Schemas['ImportRowOut'][] = []) {
  server.use(
    http.get(`*/api/v1/imports/${batch.id}`, () => HttpResponse.json(batch)),
    http.get(`*/api/v1/imports/${batch.id}/rows`, () =>
      HttpResponse.json({ items: rows, total: rows.length, page: 1, page_size: 50 }),
    ),
  )
}

describe('FR-IMP-01 import wizard', () => {
  it('uploads a file and opens the batch', async () => {
    signedInAs(MANAGER_ME)
    // jsdom's File cannot be read back from a multipart body in MSW; the API and E2E
    // tests cover the real multipart request. Here: the request is sent and followed.
    let contentType = ''
    server.use(
      http.get('*/api/v1/imports', () => HttpResponse.json(page([]))),
      http.post('*/api/v1/imports', ({ request }) => {
        contentType = request.headers.get('content-type') ?? ''
        return HttpResponse.json(BATCH, { status: 201 })
      }),
    )
    onBatch(BATCH)
    const { router } = await renderApp('/admin/imports')
    expect(await screen.findByText('No imports yet.')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Records to import'), 'contacts')
    await userEvent.upload(
      screen.getByLabelText('File'),
      new File(['Име\nАкме'], 'orgs.csv', { type: 'text/csv' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Upload' }))
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/admin/imports/${BATCH.id}`)
    })
    expect(contentType).toContain('multipart/form-data')
  })

  it('FR-IMP-01 AC1 maps columns, then saves and checks the rows', async () => {
    signedInAs(MANAGER_ME)
    onBatch(BATCH)
    let mapping: Record<string, unknown> = {}
    let validated = false
    server.use(
      http.put(`*/api/v1/imports/${BATCH.id}/mapping`, async ({ request }) => {
        mapping = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...BATCH, status: 'mapped' })
      }),
      http.post(`*/api/v1/imports/${BATCH.id}/validate`, () => {
        validated = true
        return HttpResponse.json(VALIDATED)
      }),
    )
    await renderApp(`/admin/imports/${BATCH.id}`)
    expect(await screen.findByRole('combobox', { name: 'Field for Име' })).toHaveValue('name')
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Field for Бележка' }),
      'notes',
    )
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Duplicates' }), 'update')
    await userEvent.click(screen.getByRole('button', { name: 'Save and check' }))
    await waitFor(() => {
      expect(validated).toBe(true)
    })
    expect(mapping).toEqual({
      mapping: { Име: 'name', Град: 'city', Бележка: 'notes' },
      duplicates: 'update',
    })
  })

  it('FR-IMP-01 AC1 AC2 shows invalid rows with reasons and imports without them', async () => {
    signedInAs(MANAGER_ME)
    onBatch(VALIDATED, [
      {
        row_number: 3,
        outcome: 'invalid',
        values: { name: 'Грешна', city: null, notes: null },
        errors: [
          { field: 'registration_number', code: 'validation.value_error' },
          { field: 'row', code: 'import.duplicate_in_file' },
        ],
        match: null,
        action: null,
        record_id: null,
        rollback_result: null,
      },
    ])
    let body: Record<string, unknown> = {}
    server.use(
      http.post(`*/api/v1/imports/${BATCH.id}/commit`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...VALIDATED, status: 'committed' })
      }),
    )
    await renderApp(`/admin/imports/${BATCH.id}`)
    const preview = await screen.findByRole('table', { name: 'Preview' })
    const row = within(preview).getByRole('row', { name: /Грешна/ })
    expect(row).toHaveTextContent('Invalid')
    expect(row).toHaveTextContent('Row: Repeats an earlier row of the file.')
    expect(screen.getByText('1 row is invalid.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import all' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Import, skipping invalid rows' }))
    await waitFor(() => {
      expect(body).toEqual({ mode: 'skip_invalid' })
    })
  })

  it('FR-IMP-01 AC4 only an Admin can roll back', async () => {
    const committed = {
      ...VALIDATED,
      status: 'committed' as const,
      counts: { ...VALIDATED.counts, created: 1, updated: 1, skipped: 1 },
    }
    signedInAs(MANAGER_ME)
    onBatch(committed)
    const view = await renderApp(`/admin/imports/${BATCH.id}`)
    expect(await screen.findByTestId('count-created')).toHaveTextContent('1')
    expect(screen.queryByRole('button', { name: 'Roll back import' })).not.toBeInTheDocument()
    view.unmount()

    signedInAs(ADMIN_ME)
    let rolledBack = false
    server.use(
      http.post(`*/api/v1/imports/${BATCH.id}/rollback`, () => {
        rolledBack = true
        return HttpResponse.json({
          batch: { ...committed, status: 'rolled_back' },
          archived: 1,
          reverted: 1,
          kept: [],
        })
      }),
    )
    await renderApp(`/admin/imports/${BATCH.id}`)
    await userEvent.click(await screen.findByRole('button', { name: 'Roll back import' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }))
    await waitFor(() => {
      expect(rolledBack).toBe(true)
    })
  })

  it('is hidden from Sales Reps', async () => {
    signedInAs(REP_ME)
    await renderApp('/')
    await screen.findByRole('navigation', { name: 'Main navigation' })
    expect(screen.queryByRole('link', { name: 'Import' })).not.toBeInTheDocument()
  })
})
