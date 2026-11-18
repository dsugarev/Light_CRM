import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { api, ApiError, call } from '@/api/client'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { useSectionCrumbs } from '@/components/useSectionCrumbs'
import { Pagination } from '@/components/Pagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useErrorText } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import {
  DELIVERY_STATUSES,
  LOGGED_EVENT_TYPES,
  type DeliveryStatus,
  type IntegrationClient,
} from './integrationValues'

const PAGE_SIZE = 25

function StatusBadge({ status }: { status: DeliveryStatus }) {
  const { t } = useTranslation('integrations')
  const variant =
    status === 'failed' ? 'destructive' : status === 'succeeded' ? 'secondary' : 'outline'
  return <Badge variant={variant}>{t(`deliveries.status.${status}`)}</Badge>
}

/** FR-INT-07 AC3, FR-INT-12: the delivery log, filtered by client, status and event type. */
export function DeliveriesPage() {
  const { t } = useTranslation('integrations')
  const crumbs = useSectionCrumbs()
  const locale = useLocale()
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get('page') ?? '1') || 1)
  const clientId = params.get('client_id') ?? ''
  const status = (params.get('status') ?? '') as DeliveryStatus | ''
  const eventType = params.get('event_type') ?? ''
  const clients = useQuery({
    queryKey: ['integration-clients'],
    queryFn: () => call(api.GET('/api/v1/integration-clients')),
  })
  const deliveries = useQuery({
    queryKey: ['webhook-deliveries', params.toString()],
    placeholderData: keepPreviousData,
    queryFn: () =>
      call(
        api.GET('/api/v1/webhook-deliveries', {
          params: {
            query: {
              page,
              page_size: PAGE_SIZE,
              ...(clientId ? { client_id: clientId } : {}),
              ...(status ? { status } : {}),
              ...(eventType ? { event_type: eventType } : {}),
            },
          },
        }),
      ),
  })
  const setFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(name, value)
    else next.delete(name)
    next.delete('page')
    setParams(next, { replace: true })
  }
  const names = new Map((clients.data ?? []).map((c: IntegrationClient) => [c.id, c.name]))
  return (
    <section className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader title={t('deliveries.title')} breadcrumbs={[crumbs.integrations]} />
      <div className="grid gap-3 sm:grid-cols-3">
        <FormField label={t('deliveries.client')}>
          {(control) => (
            <NativeSelect
              {...control}
              value={clientId}
              onChange={(e) => {
                setFilter('client_id', e.target.value)
              }}
            >
              <option value="">{t('deliveries.any')}</option>
              {(clients.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <FormField label={t('deliveries.statusLabel')}>
          {(control) => (
            <NativeSelect
              {...control}
              value={status}
              onChange={(e) => {
                setFilter('status', e.target.value)
              }}
            >
              <option value="">{t('deliveries.any')}</option>
              {DELIVERY_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`deliveries.status.${s}`)}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <FormField label={t('deliveries.eventType')}>
          {(control) => (
            <NativeSelect
              {...control}
              value={eventType}
              onChange={(e) => {
                setFilter('event_type', e.target.value)
              }}
            >
              <option value="">{t('deliveries.any')}</option>
              {LOGGED_EVENT_TYPES.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
      </div>
      {deliveries.isError ? (
        <ErrorState
          error={deliveries.error}
          onRetry={() => {
            void deliveries.refetch()
          }}
        />
      ) : null}
      {deliveries.data ? (
        <>
          <Table>
            <caption className="sr-only">{t('deliveries.title')}</caption>
            <TableHeader>
              <TableRow>
                <TableHead>{t('deliveries.created')}</TableHead>
                <TableHead>{t('deliveries.client')}</TableHead>
                <TableHead>{t('deliveries.eventType')}</TableHead>
                <TableHead>{t('deliveries.statusLabel')}</TableHead>
                <TableHead className="text-right">{t('deliveries.attempts')}</TableHead>
                <TableHead>{t('deliveries.lastResult')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {deliveries.data.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6}>
                    <EmptyState />
                  </TableCell>
                </TableRow>
              ) : (
                deliveries.data.items.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell>
                      <Link
                        to={`/admin/integrations/deliveries/${d.id}`}
                        className="hover:underline"
                      >
                        {formatDateTime(d.created_at, locale)}
                      </Link>
                    </TableCell>
                    <TableCell>{names.get(d.client_id) ?? ''}</TableCell>
                    <TableCell className="font-mono text-xs">{d.event_type}</TableCell>
                    <TableCell>
                      <StatusBadge status={d.status} />
                    </TableCell>
                    <TableCell className="text-right">{d.attempt_count}</TableCell>
                    <TableCell>{d.last_status_code ?? d.last_error ?? ''}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={deliveries.data.total}
            onPageChange={(p) => {
              const next = new URLSearchParams(params)
              next.set('page', String(p))
              setParams(next, { replace: true })
            }}
          />
        </>
      ) : deliveries.isPending ? (
        <Loading variant="table" />
      ) : null}
    </section>
  )
}

/** One delivery with every attempt; redeliver queues the event again. */
export function DeliveryPage() {
  const { deliveryId = '' } = useParams()
  const { t } = useTranslation('integrations')
  const crumbs = useSectionCrumbs()
  const locale = useLocale()
  const errorText = useErrorText()
  const queryClient = useQueryClient()
  const delivery = useQuery({
    queryKey: ['webhook-deliveries', deliveryId],
    queryFn: () =>
      call(
        api.GET('/api/v1/webhook-deliveries/{delivery_id}', {
          params: { path: { delivery_id: deliveryId } },
        }),
      ),
    // Follow a queued delivery (e.g. a test event) until the worker has tried it.
    refetchInterval: (query) =>
      query.state.data && ['pending'].includes(query.state.data.status) ? 2000 : false,
  })
  const redeliver = useMutation({
    mutationFn: () =>
      call(
        api.POST('/api/v1/webhook-deliveries/{delivery_id}/redeliver', {
          params: { path: { delivery_id: deliveryId } },
        }),
      ),
    onSuccess: async () => {
      toast.success(t('deliveries.redelivered'))
      await queryClient.invalidateQueries({ queryKey: ['webhook-deliveries'] })
      await queryClient.invalidateQueries({ queryKey: ['integration-clients'] })
    },
    onError: (error) => {
      toast.error(errorText(error instanceof ApiError ? error.code : undefined))
    },
  })
  if (delivery.isError)
    return (
      <ErrorState
        error={delivery.error}
        onRetry={() => {
          void delivery.refetch()
        }}
      />
    )
  if (!delivery.data) return <Loading />
  const d = delivery.data
  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-4">
      <PageHeader
        title={d.event_type}
        breadcrumbs={[
          crumbs.integrations,
          { label: t('deliveries.title'), to: '/admin/integrations/deliveries' },
        ]}
        actions={
          <Button
            type="button"
            variant="outline"
            disabled={redeliver.isPending}
            onClick={() => {
              redeliver.mutate()
            }}
          >
            {t('deliveries.redeliver')}
          </Button>
        }
      />
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
        <dt className="text-muted-foreground">{t('deliveries.statusLabel')}</dt>
        <dd>
          <StatusBadge status={d.status} />
        </dd>
        <dt className="text-muted-foreground">{t('deliveries.url')}</dt>
        <dd className="font-mono break-all">{d.url}</dd>
        <dt className="text-muted-foreground">{t('deliveries.eventId')}</dt>
        <dd className="font-mono">{d.event_id}</dd>
        <dt className="text-muted-foreground">{t('deliveries.occurred')}</dt>
        <dd>{formatDateTime(d.occurred_at, locale)}</dd>
        {d.next_attempt_at ? (
          <>
            <dt className="text-muted-foreground">{t('deliveries.nextAttempt')}</dt>
            <dd>{formatDateTime(d.next_attempt_at, locale)}</dd>
          </>
        ) : null}
        {d.delivered_at ? (
          <>
            <dt className="text-muted-foreground">{t('deliveries.delivered')}</dt>
            <dd>{formatDateTime(d.delivered_at, locale)}</dd>
          </>
        ) : null}
      </dl>
      <Table>
        <caption className="sr-only">{t('deliveries.attempts')}</caption>
        <TableHeader>
          <TableRow>
            <TableHead>#</TableHead>
            <TableHead>{t('deliveries.attemptedAt')}</TableHead>
            <TableHead>{t('deliveries.result')}</TableHead>
            <TableHead className="text-right">{t('deliveries.duration')}</TableHead>
            <TableHead>{t('deliveries.response')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {d.attempts.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-muted-foreground">
                {t('deliveries.noAttempts')}
              </TableCell>
            </TableRow>
          ) : (
            d.attempts.map((a) => (
              <TableRow key={a.number}>
                <TableCell>{a.number}</TableCell>
                <TableCell>{formatDateTime(a.attempted_at, locale)}</TableCell>
                <TableCell>
                  {a.status_code ?? (a.error ? t(`deliveries.errors.${a.error}`, a.error) : '')}
                </TableCell>
                <TableCell className="text-right">
                  {t('deliveries.ms', { ms: a.duration_ms })}
                </TableCell>
                <TableCell className="max-w-md font-mono text-xs break-all whitespace-pre-wrap">
                  {a.response_excerpt ?? ''}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </section>
  )
}
