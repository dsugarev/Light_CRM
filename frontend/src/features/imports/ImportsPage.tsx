import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

import { api, ApiError, asPage, call } from '@/api/client'
import { DataTable, type Column } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { download } from '@/features/reports/download'
import { useNotify } from '@/lib/notify'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { ENTITY_TYPES, uploadImport, type EntityType, type ImportBatch } from './upload'

import { ImportStatusBadge } from './ImportStatusBadge'

const PAGE_SIZE = 25
const ACCEPT = '.xlsx,.csv'
const LANGUAGES = ['en', 'bg'] as const

/** FR-IMP-01: past imports and a new upload, with templates to download. */
export function ImportsPage() {
  const { t } = useTranslation('imports')
  const locale = useLocale()
  const [page, setPage] = useState(1)
  const batches = useQuery({
    queryKey: ['imports', page],
    placeholderData: keepPreviousData,
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/imports', { params: { query: { page, page_size: PAGE_SIZE } } }),
        ),
      ),
  })
  const columns: Column<ImportBatch>[] = [
    {
      key: 'file',
      header: t('list.file'),
      cell: (b) => (
        <Link to={`/admin/imports/${b.id}`} className="font-medium hover:underline">
          {b.file_name}
        </Link>
      ),
    },
    { key: 'type', header: t('list.type'), cell: (b) => t(`entity.${b.entity_type}`) },
    {
      key: 'status',
      header: t('list.status'),
      cell: (b) => <ImportStatusBadge status={b.status} />,
    },
    { key: 'rows', header: t('list.rows'), cell: (b) => b.counts.rows, className: 'text-right' },
    {
      key: 'created',
      header: t('list.created'),
      cell: (b) => `${formatDateTime(b.created_at, locale)} · ${b.created_by?.full_name ?? ''}`,
    },
  ]
  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader title={t('title')} />
      <NewImport />
      {batches.isError ? (
        <ErrorState
          error={batches.error}
          onRetry={() => {
            void batches.refetch()
          }}
        />
      ) : null}
      {batches.data ? (
        <>
          <DataTable
            busy={batches.isPlaceholderData}
            caption={t('list.title')}
            columns={columns}
            rows={batches.data.items}
            rowKey={(b) => b.id}
            rowHref={(b) => `/admin/imports/${b.id}`}
            sort="-created_at"
            onSort={() => undefined}
            empty={t('list.none')}
          />
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={batches.data.total}
            onPageChange={setPage}
          />
        </>
      ) : batches.isPending ? (
        <Loading variant="table" />
      ) : null}
    </section>
  )
}

function NewImport() {
  const { t } = useTranslation('imports')
  const notify = useNotify()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [entity, setEntity] = useState<EntityType>('organizations')
  const [file, setFile] = useState<File | null>(null)
  const start = useMutation({
    mutationFn: () => {
      if (!file) throw new ApiError(422, { code: 'import.invalid_file' })
      return uploadImport(entity, file)
    },
    onSuccess: async (batch) => {
      await queryClient.invalidateQueries({ queryKey: ['imports'] })
      await navigate(`/admin/imports/${batch.id}`)
    },
  })
  const template = useMutation({
    mutationFn: (language: (typeof LANGUAGES)[number]) =>
      download(`/api/v1/imports/templates/${entity}`, `locale=${language}`),
    onError: (error) => {
      notify.error(error)
    },
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('new.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          aria-label={t('new.title')}
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            start.mutate()
          }}
        >
          <FormMessage error={start.error instanceof ApiError ? start.error.code : null} />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={t('new.type')} required>
              {(control) => (
                <NativeSelect
                  {...control}
                  value={entity}
                  onChange={(e) => {
                    setEntity(e.target.value as EntityType)
                  }}
                >
                  {ENTITY_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {t(`entity.${type}`)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label={t('new.file')} required hint={t('new.fileHint')}>
              {(control) => (
                <Input
                  {...control}
                  type="file"
                  accept={ACCEPT}
                  onChange={(e) => {
                    setFile(e.target.files?.[0] ?? null)
                  }}
                />
              )}
            </FormField>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={!file || start.isPending}>
              {t('new.upload')}
            </Button>
            <span className="text-sm text-muted-foreground">{t('new.templates')}</span>
            {LANGUAGES.map((language) => (
              <Button
                key={language}
                type="button"
                size="sm"
                variant="outline"
                disabled={template.isPending}
                onClick={() => {
                  template.mutate(language)
                }}
              >
                {t(`new.template.${language}`)}
              </Button>
            ))}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
