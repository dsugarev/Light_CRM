import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

import { api, ApiError, call } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { CopyField } from '@/components/CopyField'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useNotify } from '@/lib/notify'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { EVENT_TYPES, type IntegrationClient, type Subscription } from './integrationValues'

/** FR-INT-07, 12: a client's webhook subscriptions, with test, rotation and removal. */
export function Webhooks({ client }: { client: IntegrationClient }) {
  const { t } = useTranslation('integrations')
  const [secret, setSecret] = useState<string | null>(null)
  const subscriptions = useQuery({
    queryKey: ['webhook-subscriptions', client.id],
    queryFn: () =>
      call(
        api.GET('/api/v1/integration-clients/{client_id}/webhook-subscriptions', {
          params: { path: { client_id: client.id } },
        }),
      ),
  })
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t('webhooks.title')}</CardTitle>
        <Link
          to={`/admin/integrations/deliveries?client_id=${client.id}`}
          className="text-sm hover:underline"
        >
          {t('webhooks.log')}
        </Link>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {secret ? (
          <Alert>
            <AlertTitle>{t('webhooks.secretOnceTitle')}</AlertTitle>
            <AlertDescription className="flex flex-col gap-2">
              <span>{t('webhooks.secretOnceText')}</span>
              <CopyField value={secret} label={t('webhooks.secret')} />
            </AlertDescription>
          </Alert>
        ) : null}
        {subscriptions.data ? (
          subscriptions.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('webhooks.none')}</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {subscriptions.data.map((s) => (
                <SubscriptionItem key={s.id} subscription={s} onSecret={setSecret} />
              ))}
            </ul>
          )
        ) : (
          <Loading variant="table" />
        )}
        <NewSubscription clientId={client.id} onSecret={setSecret} />
      </CardContent>
    </Card>
  )
}

function useRefresh(clientId: string) {
  const queryClient = useQueryClient()
  return async () => {
    await queryClient.invalidateQueries({ queryKey: ['webhook-subscriptions', clientId] })
    await queryClient.invalidateQueries({ queryKey: ['integration-clients'] })
  }
}

function SubscriptionItem({
  subscription: s,
  onSecret,
}: {
  subscription: Subscription
  onSecret: (secret: string) => void
}) {
  const { t } = useTranslation('integrations')
  const locale = useLocale()
  const navigate = useNavigate()
  const notify = useNotify()
  const refresh = useRefresh(s.client_id)
  const path = { params: { path: { subscription_id: s.id } } }
  const onError = (error: Error) => {
    notify.error(error)
  }
  const toggle = useMutation({
    mutationFn: () =>
      call(
        api.PATCH('/api/v1/webhook-subscriptions/{subscription_id}', {
          ...path,
          body: { is_active: !s.is_active || s.suspended_at !== null },
        }),
      ),
    onSuccess: refresh,
    onError,
  })
  const test = useMutation({
    mutationFn: () => call(api.POST('/api/v1/webhook-subscriptions/{subscription_id}/test', path)),
    onSuccess: async (delivery) => {
      notify.success(t('webhooks.testQueued'))
      await navigate(`/admin/integrations/deliveries/${delivery.id}`)
    },
    onError,
  })
  const rotate = useMutation({
    mutationFn: () =>
      call(api.POST('/api/v1/webhook-subscriptions/{subscription_id}/rotate-secret', path)),
    onSuccess: async (result) => {
      onSecret(result.secret)
      await refresh()
    },
    onError,
  })
  const remove = useMutation({
    mutationFn: () => call(api.DELETE('/api/v1/webhook-subscriptions/{subscription_id}', path)),
    onSuccess: async () => {
      notify.success(t('webhooks.removed'))
      await refresh()
    },
    onError,
  })
  const state = s.suspended_at
    ? t('webhooks.suspended')
    : s.is_active
      ? t('status.active')
      : t('status.inactive')
  const counts = s.deliveries_24h
  return (
    <li className="flex flex-col gap-2 rounded-md border p-3" aria-label={s.url}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm break-all">{s.url}</span>
        <Badge variant={s.suspended_at ? 'destructive' : s.is_active ? 'success' : 'outline'}>
          {state}
        </Badge>
      </div>
      <div className="flex flex-wrap gap-1">
        {s.event_types.map((e) => (
          <code key={e} className="rounded bg-muted px-1 text-xs">
            {e === '*' ? t('webhooks.allEvents') : e}
          </code>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">
        {t('webhooks.counts', {
          succeeded: counts.succeeded,
          failing: counts.retrying + counts.failed,
          pending: counts.pending,
        })}
        {s.previous_secret_valid_until
          ? ` · ${t('webhooks.previousSecret', {
              until: formatDateTime(s.previous_secret_valid_until, locale),
            })}`
          : ''}
      </p>
      {s.suspended_at ? (
        <p className="text-sm text-destructive">
          {t('webhooks.suspendedText', { at: formatDateTime(s.suspended_at, locale) })}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={test.isPending}
          onClick={() => {
            test.mutate()
          }}
        >
          {t('webhooks.test')}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={toggle.isPending}
          onClick={() => {
            toggle.mutate()
          }}
        >
          {s.is_active && !s.suspended_at ? t('webhooks.pause') : t('webhooks.resume')}
        </Button>
        <ConfirmButton
          label={t('webhooks.rotate')}
          title={t('webhooks.rotate')}
          description={t('webhooks.confirmRotate')}
          variant="outline"
          onConfirm={() => {
            rotate.mutate()
          }}
        />
        <ConfirmButton
          label={t('webhooks.remove')}
          title={t('webhooks.remove')}
          description={t('webhooks.confirmRemove', { url: s.url })}
          variant="destructive"
          onConfirm={() => {
            remove.mutate()
          }}
        />
      </div>
    </li>
  )
}

function NewSubscription({
  clientId,
  onSecret,
}: {
  clientId: string
  onSecret: (secret: string) => void
}) {
  const notify = useNotify()
  const { t } = useTranslation('integrations')
  const refresh = useRefresh(clientId)
  const [url, setUrl] = useState('')
  const [events, setEvents] = useState<string[]>([])
  const create = useMutation({
    mutationFn: () =>
      call(
        api.POST('/api/v1/integration-clients/{client_id}/webhook-subscriptions', {
          params: { path: { client_id: clientId } },
          body: { url: url.trim(), event_types: events, is_active: true },
        }),
      ),
    onSuccess: async (created) => {
      onSecret(created.secret)
      setUrl('')
      setEvents([])
      notify.success(t('webhooks.created'))
      await refresh()
    },
  })
  const error = create.error instanceof ApiError ? create.error : null
  const fieldError = (field: string) => error?.errors.find((e) => e.field.startsWith(field))?.code
  return (
    <form
      aria-label={t('webhooks.new')}
      className="flex flex-col gap-3 border-t pt-4"
      onSubmit={(event) => {
        event.preventDefault()
        create.mutate()
      }}
    >
      <FormMessage error={error?.errors.length === 0 ? error.code : null} />
      <FormField
        label={t('webhooks.url')}
        required
        hint={t('webhooks.urlHint')}
        error={fieldError('url')}
      >
        {(control) => (
          <Input
            {...control}
            type="url"
            value={url}
            maxLength={500}
            onChange={(e) => {
              setUrl(e.target.value)
            }}
          />
        )}
      </FormField>
      <fieldset className="grid gap-1 sm:grid-cols-2">
        <legend className="mb-2 text-sm font-medium">{t('webhooks.events')}</legend>
        {EVENT_TYPES.map((type) => (
          <label key={type} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={events.includes(type)}
              onChange={(e) => {
                setEvents(e.target.checked ? [...events, type] : events.filter((v) => v !== type))
              }}
            />
            {type === '*' ? t('webhooks.allEvents') : <code>{type}</code>}
          </label>
        ))}
      </fieldset>
      <Button
        type="submit"
        className="self-start"
        disabled={!url.trim() || events.length === 0 || create.isPending}
      >
        {t('webhooks.create')}
      </Button>
    </form>
  )
}
