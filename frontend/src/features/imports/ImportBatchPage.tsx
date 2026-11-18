import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { api, ApiError, call, type Schemas } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorState } from '@/components/ErrorState'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { useSectionCrumbs } from '@/components/useSectionCrumbs'
import { Pagination } from '@/components/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useMe } from '@/features/auth/useMe'
import { useErrorText } from '@/lib/errors'
import { useLocale } from '@/lib/useLocale'

import type { ImportBatch, ImportRow } from './upload'

type Outcome = NonNullable<ImportRow['outcome']>
const OUTCOMES: readonly Outcome[] = ['invalid', 'duplicate', 'valid']
const PAGE_SIZE = 50
const IGNORE = ''
const WITH_DUPLICATES = new Set(['organizations', 'contacts'])
const RESULTS = ['archived', 'reverted', 'changed_since_import', 'blocked'] as const

/** `blocked:<code>` and future values fall back to "blocked". */
function resultKey(result: string): (typeof RESULTS)[number] {
  const base = result.split(':')[0]
  return RESULTS.find((r) => r === base) ?? 'blocked'
}

/** FR-IMP-01: map columns, check the preview, commit; Admins can roll a batch back. */
export function ImportBatchPage() {
  const { batchId = '' } = useParams()
  const { t } = useTranslation('imports')
  const crumbs = useSectionCrumbs()
  const batch = useQuery({
    queryKey: ['imports', batchId],
    queryFn: () =>
      call(api.GET('/api/v1/imports/{batch_id}', { params: { path: { batch_id: batchId } } })),
  })
  if (batch.isError)
    return (
      <ErrorState
        error={batch.error}
        onRetry={() => {
          void batch.refetch()
        }}
      />
    )
  if (!batch.data) return <Loading />
  const b = batch.data
  const editable = b.status === 'uploaded' || b.status === 'mapped' || b.status === 'validated'
  return (
    <section className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        breadcrumbs={[crumbs.imports]}
        title={b.file_name}
        actions={
          <span className="flex items-center gap-2">
            <Badge variant="outline">{t(`entity.${b.entity_type}`)}</Badge>
            <Badge variant="secondary">{t(`status.${b.status}`)}</Badge>
          </span>
        }
      />
      <Counts batch={b} />
      {editable ? <MappingCard key={`${b.id}-${b.status}`} batch={b} /> : null}
      {b.status === 'validated' ? <CommitCard batch={b} /> : null}
      {b.status !== 'uploaded' && b.status !== 'mapped' ? (
        // A new step starts with its own default filter (invalid rows while checking).
        <Preview key={b.status} batch={b} />
      ) : null}
      {b.status === 'committed' ? <RollbackCard batch={b} /> : null}
    </section>
  )
}

function useBatchMutation<V>(batchId: string, fn: (v: V) => Promise<unknown>, message: string) {
  const queryClient = useQueryClient()
  const errorText = useErrorText()
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['imports'] })
      await queryClient.invalidateQueries({ queryKey: ['import-rows', batchId] })
      toast.success(message)
    },
    onError: (error) => {
      if (!(error instanceof ApiError && error.errors.length > 0)) {
        toast.error(errorText(error instanceof ApiError ? error.code : undefined))
      }
    },
  })
}

function Counts({ batch }: { batch: ImportBatch }) {
  const { t } = useTranslation('imports')
  const shown = (
    batch.status === 'committed' || batch.status === 'rolled_back'
      ? (['rows', 'created', 'updated', 'skipped'] as const)
      : (['rows', 'valid', 'invalid', 'duplicate'] as const)
  ).filter((key) => key === 'rows' || batch.status !== 'uploaded')
  return (
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {shown.map((key) => (
        <div key={key} className="rounded-lg border p-3">
          <dt className="text-sm text-muted-foreground">{t(`counts.${key}`)}</dt>
          <dd className="text-2xl font-semibold" data-testid={`count-${key}`}>
            {batch.counts[key]}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function MappingCard({ batch }: { batch: ImportBatch }) {
  const { t } = useTranslation('imports')
  const locale = useLocale()
  const [mapping, setMapping] = useState<Record<string, string>>(() =>
    Object.fromEntries(batch.columns.map((c) => [c, batch.mapping[c] ?? IGNORE])),
  )
  const [duplicates, setDuplicates] = useState<'skip' | 'update'>(batch.duplicate_mode ?? 'skip')
  const path = { params: { path: { batch_id: batch.id } } }
  const save = useBatchMutation(
    batch.id,
    () =>
      call(
        api.PUT('/api/v1/imports/{batch_id}/mapping', {
          ...path,
          body: {
            mapping: Object.fromEntries(
              Object.entries(mapping).map(([column, key]) => [column, key === IGNORE ? null : key]),
            ),
            duplicates,
          },
        }),
      ).then(() => call(api.POST('/api/v1/imports/{batch_id}/validate', path))),
    t('toasts.validated'),
  )
  const label = (f: Schemas['FieldInfo']) =>
    `${locale === 'bg' ? f.name_bg : f.name_en}${f.required ? ' *' : ''}`
  const fieldErrors = save.error instanceof ApiError ? save.error.errors : []
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('mapping.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">{t('mapping.help')}</p>
        {fieldErrors.map((e) => (
          <FormMessage key={`${e.field}-${e.code}`} error={e.code} />
        ))}
        <Table>
          <caption className="sr-only">{t('mapping.title')}</caption>
          <TableHeader>
            <TableRow>
              <TableHead>{t('mapping.column')}</TableHead>
              <TableHead>{t('mapping.field')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {batch.columns.map((column) => (
              <TableRow key={column}>
                <TableCell className="font-medium">{column}</TableCell>
                <TableCell>
                  <NativeSelect
                    aria-label={t('mapping.fieldFor', { column })}
                    value={mapping[column] ?? IGNORE}
                    onChange={(e) => {
                      setMapping((m) => ({ ...m, [column]: e.target.value }))
                    }}
                  >
                    <option value={IGNORE}>{t('mapping.ignore')}</option>
                    {batch.fields.map((f) => (
                      <option key={f.key} value={f.key}>
                        {label(f)}
                      </option>
                    ))}
                  </NativeSelect>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {WITH_DUPLICATES.has(batch.entity_type) ? (
          <NativeSelect
            aria-label={t('mapping.duplicates')}
            value={duplicates}
            className="w-72"
            onChange={(e) => {
              setDuplicates(e.target.value as 'skip' | 'update')
            }}
          >
            <option value="skip">{t('mapping.skip')}</option>
            <option value="update">{t('mapping.update')}</option>
          </NativeSelect>
        ) : null}
        <Button
          type="button"
          className="self-start"
          disabled={save.isPending}
          onClick={() => {
            save.mutate(undefined)
          }}
        >
          {t('mapping.validate')}
        </Button>
      </CardContent>
    </Card>
  )
}

function CommitCard({ batch }: { batch: ImportBatch }) {
  const { t } = useTranslation('imports')
  const navigate = useNavigate()
  const path = { params: { path: { batch_id: batch.id } } }
  const commit = useBatchMutation(
    batch.id,
    (mode: 'strict' | 'skip_invalid') =>
      call(api.POST('/api/v1/imports/{batch_id}/commit', { ...path, body: { mode } })),
    t('toasts.committed'),
  )
  const discard = useBatchMutation(
    batch.id,
    async () => {
      await call(api.DELETE('/api/v1/imports/{batch_id}', path))
      await navigate('/admin/imports')
    },
    t('toasts.discarded'),
  )
  const invalid = batch.counts.invalid > 0
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('commit.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-2">
        <p className="w-full text-sm text-muted-foreground">
          {invalid ? t('commit.hasInvalid', { count: batch.counts.invalid }) : t('commit.allValid')}
        </p>
        <Button
          type="button"
          disabled={invalid || commit.isPending}
          onClick={() => {
            commit.mutate('strict')
          }}
        >
          {t('commit.strict')}
        </Button>
        {invalid ? (
          <Button
            type="button"
            variant="outline"
            disabled={commit.isPending}
            onClick={() => {
              commit.mutate('skip_invalid')
            }}
          >
            {t('commit.skipInvalid')}
          </Button>
        ) : null}
        <ConfirmButton
          label={t('commit.discard')}
          title={t('commit.discard')}
          description={t('commit.confirmDiscard')}
          variant="destructive"
          onConfirm={() => {
            discard.mutate(undefined)
          }}
        />
      </CardContent>
    </Card>
  )
}

function Preview({ batch }: { batch: ImportBatch }) {
  const { t } = useTranslation('imports')
  const locale = useLocale()
  const errorText = useErrorText()
  const [outcome, setOutcome] = useState<Outcome | ''>(
    batch.status === 'validated' ? 'invalid' : '',
  )
  const [page, setPage] = useState(1)
  const rows = useQuery({
    queryKey: ['import-rows', batch.id, outcome, page],
    placeholderData: keepPreviousData,
    queryFn: () =>
      call(
        api.GET('/api/v1/imports/{batch_id}/rows', {
          params: {
            path: { batch_id: batch.id },
            query: { page, page_size: PAGE_SIZE, ...(outcome ? { outcome: [outcome] } : {}) },
          },
        }),
      ),
  })
  const fieldName = (key: string) => {
    const field = batch.fields.find((f) => f.key === key)
    if (!field) return key === 'row' ? t('preview.row') : key
    return locale === 'bg' ? field.name_bg : field.name_en
  }
  const shown = batch.fields.slice(0, 3)
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t('preview.title')}</CardTitle>
        <NativeSelect
          aria-label={t('preview.filter')}
          value={outcome}
          className="w-48"
          onChange={(e) => {
            setOutcome(e.target.value as Outcome | '')
            setPage(1)
          }}
        >
          <option value="">{t('preview.all')}</option>
          {OUTCOMES.map((o) => (
            <option key={o} value={o}>
              {t(`outcome.${o}`)}
            </option>
          ))}
        </NativeSelect>
      </CardHeader>
      <CardContent>
        {rows.data ? (
          <>
            <Table>
              <caption className="sr-only">{t('preview.title')}</caption>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('preview.row')}</TableHead>
                  <TableHead>{t('preview.outcome')}</TableHead>
                  {shown.map((f) => (
                    <TableHead key={f.key}>{fieldName(f.key)}</TableHead>
                  ))}
                  <TableHead>{t('preview.details')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.data.items.map((row) => (
                  <TableRow key={row.row_number}>
                    <TableCell>{row.row_number}</TableCell>
                    <TableCell>
                      {row.action ? (
                        <Badge variant="secondary">{t(`action.${row.action}`)}</Badge>
                      ) : row.outcome ? (
                        <Badge variant={row.outcome === 'invalid' ? 'destructive' : 'secondary'}>
                          {t(`outcome.${row.outcome}`)}
                        </Badge>
                      ) : null}
                    </TableCell>
                    {shown.map((f) => (
                      <TableCell key={f.key}>{row.values[f.key] ?? ''}</TableCell>
                    ))}
                    <TableCell className="text-sm">
                      {row.errors.map((e) => (
                        <div key={`${e.field}-${e.code}`}>
                          {`${fieldName(e.field)}: ${errorText(e.code)}`}
                        </div>
                      ))}
                      {row.match ? (
                        <div>{t('preview.matches', { name: row.match.name })}</div>
                      ) : null}
                      {row.rollback_result ? (
                        <div>{t(`rollback.result.${resultKey(row.rollback_result)}`)}</div>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={rows.data.total}
              onPageChange={setPage}
            />
          </>
        ) : (
          <Loading variant="table" />
        )}
      </CardContent>
    </Card>
  )
}

function RollbackCard({ batch }: { batch: ImportBatch }) {
  const { t } = useTranslation('imports')
  const { data: me } = useMe()
  const [report, setReport] = useState<Schemas['RollbackReport'] | null>(null)
  const rollback = useBatchMutation(
    batch.id,
    async () => {
      setReport(
        await call(
          api.POST('/api/v1/imports/{batch_id}/rollback', {
            params: { path: { batch_id: batch.id } },
          }),
        ),
      )
    },
    t('toasts.rolledBack'),
  )
  if (me?.role !== 'admin') return null
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('rollback.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground">{t('rollback.help')}</p>
        {report ? (
          <p className="text-sm">
            {t('rollback.done', {
              archived: report.archived,
              reverted: report.reverted,
              kept: report.kept.length,
            })}
          </p>
        ) : null}
        <ConfirmButton
          label={t('rollback.button')}
          title={t('rollback.button')}
          description={t('rollback.confirm', {
            count: batch.counts.created + batch.counts.updated,
          })}
          variant="destructive"
          onConfirm={() => {
            rollback.mutate(undefined)
          }}
        />
      </CardContent>
    </Card>
  )
}
