import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'
import { toast } from 'sonner'

import { api, ApiError, call, type Schemas } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { CopyField } from '@/components/CopyField'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Textarea } from '@/components/Textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useUserLookup } from '@/features/auth/useUserLookup'
import { referenceName } from '@/features/reference/useReferenceList'
import { useErrorText } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { parseAllowlist, type IntegrationClient, type Scope } from './integrationValues'
import { ScopePicker } from './ScopePicker'

/** FR-INT-01, 02, 12: a client's settings, activation and API keys. */
export function ClientPage() {
  const { clientId = '' } = useParams()
  const { t } = useTranslation('integrations')
  const locale = useLocale()
  const client = useQuery({
    queryKey: ['integration-clients', clientId],
    queryFn: () =>
      call(
        api.GET('/api/v1/integration-clients/{client_id}', {
          params: { path: { client_id: clientId } },
        }),
      ),
  })
  if (client.isError) return <ErrorState error={client.error} />
  if (!client.data) return <Loading />
  const c = client.data
  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title={c.name}
        actions={
          <span className="flex items-center gap-2">
            <Badge variant="outline">{referenceName(c.system, locale)}</Badge>
            <Badge variant={c.is_active ? 'secondary' : 'outline'}>
              {c.is_active ? t('status.active') : t('status.inactive')}
            </Badge>
          </span>
        }
      />
      <p className="text-sm text-muted-foreground">
        {t('detail.usage', {
          requests: c.usage.requests_24h,
          errors: c.usage.errors_24h,
          lastUsed: c.last_used_at ? formatDateTime(c.last_used_at, locale) : t('list.never'),
        })}
      </p>
      <SettingsCard key={c.updated_at} client={c} />
      <Keys client={c} />
    </section>
  )
}

function useClientMutation<V>(clientId: string, fn: (v: V) => Promise<unknown>, message: string) {
  const queryClient = useQueryClient()
  const errorText = useErrorText()
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['integration-clients'] })
      await queryClient.invalidateQueries({ queryKey: ['api-keys', clientId] })
      toast.success(message)
    },
    onError: (error) => {
      if (!(error instanceof ApiError && error.errors.length > 0)) {
        toast.error(errorText(error instanceof ApiError ? error.code : undefined))
      }
    },
  })
}

function SettingsCard({ client }: { client: IntegrationClient }) {
  const { t } = useTranslation('integrations')
  const users = useUserLookup(true)
  const path = { params: { path: { client_id: client.id } } }
  const [draft, setDraft] = useState({
    name: client.name,
    scopes: client.scopes,
    owner: client.default_owner?.id ?? '',
    allowlist: client.ip_allowlist.join('\n'),
    contact: client.technical_contact ?? '',
    rateLimit: String(client.rate_limit_per_minute),
  })
  const save = useClientMutation(
    client.id,
    () =>
      call(
        api.PATCH('/api/v1/integration-clients/{client_id}', {
          ...path,
          body: {
            name: draft.name.trim(),
            scopes: draft.scopes,
            default_owner_id: draft.owner || null,
            ip_allowlist: parseAllowlist(draft.allowlist),
            technical_contact: draft.contact.trim() || null,
            rate_limit_per_minute: Number(draft.rateLimit),
          },
        }),
      ),
    t('toasts.saved'),
  )
  const toggle = useClientMutation(
    client.id,
    () =>
      client.is_active
        ? call(api.POST('/api/v1/integration-clients/{client_id}/deactivate', path))
        : call(api.POST('/api/v1/integration-clients/{client_id}/activate', path)),
    client.is_active ? t('toasts.deactivated') : t('toasts.activated'),
  )
  const errors = save.error instanceof ApiError ? save.error.errors : []
  const fieldError = (field: string) => errors.find((e) => e.field.startsWith(field))?.code
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t('detail.settings')}</CardTitle>
        {client.is_active ? (
          <ConfirmButton
            label={t('detail.deactivate')}
            title={t('detail.deactivate')}
            description={t('detail.confirmDeactivate', { name: client.name })}
            variant="destructive"
            onConfirm={() => {
              toggle.mutate(undefined)
            }}
          />
        ) : (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              toggle.mutate(undefined)
            }}
          >
            {t('detail.activate')}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <form
          aria-label={t('detail.settings')}
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate(undefined)
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={t('fields.name')} error={fieldError('name')}>
              {(control) => (
                <Input
                  {...control}
                  value={draft.name}
                  maxLength={100}
                  onChange={(e) => {
                    setDraft((d) => ({ ...d, name: e.target.value }))
                  }}
                />
              )}
            </FormField>
            <FormField
              label={t('fields.defaultOwner')}
              hint={t('hints.defaultOwner')}
              error={fieldError('default_owner_id')}
            >
              {(control) => (
                <NativeSelect
                  {...control}
                  value={draft.owner}
                  onChange={(e) => {
                    setDraft((d) => ({ ...d, owner: e.target.value }))
                  }}
                >
                  <option value="">{t('fields.noOwner')}</option>
                  {(users.data?.items ?? []).map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.full_name}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label={t('fields.rateLimit')} error={fieldError('rate_limit_per_minute')}>
              {(control) => (
                <Input
                  {...control}
                  inputMode="numeric"
                  value={draft.rateLimit}
                  onChange={(e) => {
                    setDraft((d) => ({ ...d, rateLimit: e.target.value }))
                  }}
                />
              )}
            </FormField>
            <FormField label={t('fields.contact')} error={fieldError('technical_contact')}>
              {(control) => (
                <Input
                  {...control}
                  value={draft.contact}
                  maxLength={300}
                  onChange={(e) => {
                    setDraft((d) => ({ ...d, contact: e.target.value }))
                  }}
                />
              )}
            </FormField>
          </div>
          <FormField
            label={t('fields.allowlist')}
            hint={t('hints.allowlist')}
            error={fieldError('ip_allowlist')}
          >
            {(control) => (
              <Textarea
                {...control}
                rows={3}
                value={draft.allowlist}
                onChange={(e) => {
                  setDraft((d) => ({ ...d, allowlist: e.target.value }))
                }}
              />
            )}
          </FormField>
          <ScopePicker
            value={draft.scopes}
            onChange={(scopes: Scope[]) => {
              setDraft((d) => ({ ...d, scopes }))
            }}
          />
          <Button type="submit" className="self-start" disabled={save.isPending}>
            {t('detail.save')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function Keys({ client }: { client: IntegrationClient }) {
  const { t } = useTranslation('integrations')
  const locale = useLocale()
  const [label, setLabel] = useState('')
  const [created, setCreated] = useState<Schemas['ApiKeyCreated'] | null>(null)
  const path = { params: { path: { client_id: client.id } } }
  const keys = useQuery({
    queryKey: ['api-keys', client.id],
    queryFn: () => call(api.GET('/api/v1/integration-clients/{client_id}/api-keys', path)),
  })
  const create = useClientMutation(
    client.id,
    async () => {
      setCreated(
        await call(
          api.POST('/api/v1/integration-clients/{client_id}/api-keys', {
            ...path,
            body: { label: label.trim() },
          }),
        ),
      )
      setLabel('')
    },
    t('toasts.keyCreated'),
  )
  const revoke = useClientMutation(
    client.id,
    (keyId: string) =>
      call(
        api.DELETE('/api/v1/integration-clients/{client_id}/api-keys/{key_id}', {
          params: { path: { client_id: client.id, key_id: keyId } },
        }),
      ),
    t('toasts.keyRevoked'),
  )
  const state = (k: Schemas['ApiKeyOut']) =>
    k.revoked_at
      ? t('keys.revoked')
      : new Date(k.expires_at) <= new Date()
        ? t('keys.expired')
        : t('keys.active')
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('keys.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {created ? (
          <Alert>
            <AlertTitle>{t('keys.onceTitle')}</AlertTitle>
            <AlertDescription className="flex flex-col gap-2">
              <span>{t('keys.onceText')}</span>
              <CopyField value={created.key} label={t('keys.newKey')} />
            </AlertDescription>
          </Alert>
        ) : null}
        {keys.data ? (
          <Table>
            <caption className="sr-only">{t('keys.title')}</caption>
            <TableHeader>
              <TableRow>
                <TableHead>{t('keys.label')}</TableHead>
                <TableHead>{t('keys.prefix')}</TableHead>
                <TableHead>{t('keys.expires')}</TableHead>
                <TableHead>{t('keys.lastUsed')}</TableHead>
                <TableHead>{t('keys.state')}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.data.map((k) => (
                <TableRow key={k.id}>
                  <TableCell>{k.label}</TableCell>
                  <TableCell className="font-mono text-xs">{k.prefix}</TableCell>
                  <TableCell>{formatDateTime(k.expires_at, locale)}</TableCell>
                  <TableCell>
                    {k.last_used_at
                      ? `${formatDateTime(k.last_used_at, locale)} · ${k.last_used_ip ?? ''}`
                      : t('list.never')}
                  </TableCell>
                  <TableCell>{state(k)}</TableCell>
                  <TableCell>
                    {k.revoked_at ? null : (
                      <ConfirmButton
                        label={t('keys.revoke')}
                        title={t('keys.revoke')}
                        description={t('keys.confirmRevoke', { label: k.label })}
                        variant="destructive"
                        onConfirm={() => {
                          revoke.mutate(k.id)
                        }}
                      />
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <Loading />
        )}
        <form
          aria-label={t('keys.create')}
          className="flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            create.mutate(undefined)
          }}
        >
          <FormField label={t('keys.label')}>
            {(control) => (
              <Input
                {...control}
                value={label}
                maxLength={100}
                onChange={(e) => {
                  setLabel(e.target.value)
                }}
              />
            )}
          </FormField>
          <Button type="submit" disabled={!label.trim() || create.isPending}>
            {t('keys.create')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
