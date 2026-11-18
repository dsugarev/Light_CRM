import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { api, ApiError, call } from '@/api/client'
import { DataTable, type Column } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { referenceName, useReferenceList } from '@/features/reference/useReferenceList'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { DEFAULT_RATE_LIMIT, type IntegrationClient, type Scope } from './integrationValues'
import { ScopePicker } from './ScopePicker'

/** FR-INT-01, 08, 12: integration clients with their status and last-24-hour figures. */
export function IntegrationsPage() {
  const { t } = useTranslation('integrations')
  const locale = useLocale()
  const clients = useQuery({
    queryKey: ['integration-clients'],
    queryFn: () => call(api.GET('/api/v1/integration-clients')),
  })
  const columns: Column<IntegrationClient>[] = [
    {
      key: 'name',
      header: t('list.name'),
      cell: (c) => (
        <Link to={`/admin/integrations/${c.id}`} className="font-medium hover:underline">
          {c.name}
        </Link>
      ),
    },
    { key: 'system', header: t('list.system'), cell: (c) => referenceName(c.system, locale) },
    {
      key: 'status',
      header: t('list.status'),
      cell: (c) => (
        <Badge variant={c.is_active ? 'secondary' : 'outline'}>
          {c.is_active ? t('status.active') : t('status.inactive')}
        </Badge>
      ),
    },
    { key: 'keys', header: t('list.keys'), cell: (c) => c.active_keys, className: 'text-right' },
    {
      key: 'usage',
      header: t('list.usage'),
      cell: (c) =>
        t('list.usageValue', { requests: c.usage.requests_24h, errors: c.usage.errors_24h }),
    },
    {
      key: 'used',
      header: t('list.lastUsed'),
      cell: (c) => (c.last_used_at ? formatDateTime(c.last_used_at, locale) : t('list.never')),
    },
  ]
  return (
    <section className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader title={t('title')} />
      {clients.isError ? <ErrorState error={clients.error} /> : null}
      {clients.data ? (
        <DataTable
          caption={t('title')}
          columns={columns}
          rows={clients.data}
          rowKey={(c) => c.id}
          sort="name"
          onSort={() => undefined}
          empty={t('list.none')}
        />
      ) : clients.isPending ? (
        <Loading />
      ) : null}
      <NewClient />
    </section>
  )
}

function NewClient() {
  const { t } = useTranslation('integrations')
  const locale = useLocale()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const systems = useReferenceList('external-systems')
  const [name, setName] = useState('')
  const [system, setSystem] = useState('')
  const [scopes, setScopes] = useState<Scope[]>([])
  const create = useMutation({
    mutationFn: () =>
      call(
        api.POST('/api/v1/integration-clients', {
          // Clients start inactive; an Admin activates them once the system owner confirms.
          body: {
            name: name.trim(),
            system,
            scopes,
            is_active: false,
            ip_allowlist: [],
            rate_limit_per_minute: DEFAULT_RATE_LIMIT,
          },
        }),
      ),
    onSuccess: async (client) => {
      await queryClient.invalidateQueries({ queryKey: ['integration-clients'] })
      toast.success(t('toasts.created'))
      await navigate(`/admin/integrations/${client.id}`)
    },
  })
  const fieldError = (field: string) =>
    create.error instanceof ApiError
      ? create.error.errors.find((e) => e.field === field)?.code
      : undefined
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
            create.mutate()
          }}
        >
          <FormMessage
            error={
              create.error instanceof ApiError && create.error.errors.length === 0
                ? create.error.code
                : null
            }
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={t('fields.name')} error={fieldError('name')}>
              {(control) => (
                <Input
                  {...control}
                  value={name}
                  maxLength={100}
                  onChange={(e) => {
                    setName(e.target.value)
                  }}
                />
              )}
            </FormField>
            <FormField label={t('fields.system')} error={fieldError('system')}>
              {(control) => (
                <NativeSelect
                  {...control}
                  value={system}
                  onChange={(e) => {
                    setSystem(e.target.value)
                  }}
                >
                  <option value="">{t('fields.chooseSystem')}</option>
                  {(systems.data ?? []).map((item) => (
                    <option key={item.id} value={item.code}>
                      {referenceName(item, locale)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
          </div>
          <ScopePicker value={scopes} onChange={setScopes} />
          <Button type="submit" className="self-start" disabled={!name.trim() || !system}>
            {t('new.create')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
