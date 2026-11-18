import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, ApiError, call } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { NativeSelect } from '@/components/NativeSelect'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useMe } from '@/features/auth/useMe'
import { referenceName, useReferenceList } from '@/features/reference/useReferenceList'
import { useNotify } from '@/lib/notify'
import { useLocale } from '@/lib/useLocale'

type Resource = 'organizations' | 'contacts' | 'leads' | 'opportunities'

/** FR-INT-04 AC4: the record's IDs in Conclusion, ERP and Billing; Admins can edit them. */
export function ExternalReferences({ resource, id }: { resource: Resource; id: string }) {
  const { t } = useTranslation('integrations')
  const locale = useLocale()
  const { data: me } = useMe()
  const isAdmin = me?.role === 'admin'
  const queryClient = useQueryClient()
  const notify = useNotify()
  const systems = useReferenceList('external-systems')
  const [system, setSystem] = useState('')
  const [externalId, setExternalId] = useState('')
  const [url, setUrl] = useState('')
  const key = ['external-references', resource, id]
  const references = useQuery({
    queryKey: key,
    queryFn: () =>
      call(
        api.GET('/api/v1/{resource}/{id}/external-references', {
          params: { path: { resource, id } },
        }),
      ),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: key })
  const save = useMutation({
    mutationFn: () =>
      call(
        api.PUT('/api/v1/{resource}/{id}/external-references/{system}', {
          params: { path: { resource, id, system } },
          body: { external_id: externalId.trim(), url: url.trim() || null },
        }),
      ),
    onSuccess: async () => {
      setExternalId('')
      setUrl('')
      await refresh()
      notify.success(t('references.saved'))
    },
  })
  const remove = useMutation({
    mutationFn: (code: string) =>
      call(
        api.DELETE('/api/v1/{resource}/{id}/external-references/{system}', {
          params: { path: { resource, id, system: code } },
        }),
      ),
    onSuccess: async () => {
      await refresh()
      notify.success(t('references.removed'))
    },
    onError: (error) => {
      notify.error(error)
    },
  })
  const items = references.data ?? []
  if (!isAdmin && items.length === 0) return null
  const saveError = save.error instanceof ApiError ? save.error : null
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('references.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('references.none')}</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {items.map((r) => (
              <li key={r.system.id} className="flex flex-wrap items-center gap-2">
                <span className="text-muted-foreground">{referenceName(r.system, locale)}</span>
                {r.url ? (
                  <a
                    className="font-medium hover:underline"
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {r.external_id}
                  </a>
                ) : (
                  <span className="font-medium">{r.external_id}</span>
                )}
                {isAdmin ? (
                  <ConfirmButton
                    label={t('references.remove')}
                    title={t('references.remove')}
                    description={t('references.confirmRemove', { id: r.external_id })}
                    variant="outline"
                    onConfirm={() => {
                      remove.mutate(r.system.code)
                    }}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {isAdmin ? (
          <form
            aria-label={t('references.add')}
            className="grid items-end gap-2 sm:grid-cols-[10rem_1fr_1fr_auto]"
            onSubmit={(event) => {
              event.preventDefault()
              save.mutate()
            }}
          >
            <FormField label={t('references.system')} required>
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
            <FormField
              label={t('references.externalId')}
              required
              error={saveError?.errors.find((e) => e.field === 'external_id')?.code}
            >
              {(control) => (
                <Input
                  {...control}
                  value={externalId}
                  maxLength={200}
                  onChange={(e) => {
                    setExternalId(e.target.value)
                  }}
                />
              )}
            </FormField>
            <FormField
              label={t('references.url')}
              error={saveError?.errors.find((e) => e.field === 'url')?.code}
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
            <Button type="submit" disabled={!system || !externalId.trim() || save.isPending}>
              {t('references.save')}
            </Button>
            <div className="sm:col-span-4">
              <FormMessage error={saveError?.errors.length === 0 ? saveError.code : null} />
            </div>
          </form>
        ) : null}
      </CardContent>
    </Card>
  )
}
