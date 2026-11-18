import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { NavLink, Navigate, useParams } from 'react-router'
import { z } from 'zod'

import { api, ApiError, call } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
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
import {
  REFERENCE_LISTS,
  useReferenceList,
  type ReferenceItem,
  type ReferenceListName,
} from '@/features/reference/useReferenceList'
import { applyServerErrors } from '@/lib/errors'
import { useNotify } from '@/lib/notify'

const schema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^[a-z0-9_]{1,50}$/, { error: 'validation.pattern_mismatch' }),
  name_en: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .max(200, { error: 'validation.string_too_long' }),
  name_bg: z
    .string()
    .trim()
    .min(1, { error: 'validation.required' })
    .max(200, { error: 'validation.string_too_long' }),
})
type Values = z.infer<typeof schema>

/** FR-ADM-02: Admins add, rename, reorder, (de)activate and delete list values. */
export function ReferenceListPage() {
  const { list = '' } = useParams()
  if (!(REFERENCE_LISTS as readonly string[]).includes(list)) {
    return <Navigate to="/admin/reference/industries" replace />
  }
  return <ReferenceListEditor key={list} list={list as ReferenceListName} />
}

function ReferenceListEditor({ list: LIST }: { list: ReferenceListName }) {
  const notify = useNotify()
  const { t } = useTranslation('admin')
  const items = useReferenceList(LIST, true)
  const queryClient = useQueryClient()
  const path = { params: { path: { list: LIST } } }
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['reference', LIST] })

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { is_active?: boolean } }) =>
      call(
        api.PATCH('/api/v1/reference/{list}/{item_id}', {
          params: { path: { list: LIST, item_id: id } },
          body,
        }),
      ),
    onSuccess: async () => {
      await refresh()
      notify.success(t('reference.saved'))
    },
  })
  const reorder = useMutation({
    mutationFn: (ids: string[]) =>
      call(api.PUT('/api/v1/reference/{list}/order', { ...path, body: ids })),
    onSuccess: refresh,
  })
  const remove = useMutation({
    mutationFn: (id: string) =>
      call(
        api.DELETE('/api/v1/reference/{list}/{item_id}', {
          params: { path: { list: LIST, item_id: id } },
        }),
      ),
    onSuccess: async () => {
      await refresh()
      notify.success(t('reference.deleted'))
    },
  })

  const move = (list: ReferenceItem[], index: number, delta: number) => {
    const ids = list.map((i) => i.id)
    const [moved] = ids.splice(index, 1)
    if (moved) ids.splice(index + delta, 0, moved)
    reorder.mutate(ids)
  }
  const error = [update.error, reorder.error, remove.error].find((e) => e instanceof ApiError)

  return (
    <section className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader title={t('reference.title')} />
      <nav aria-label={t('reference.title')} className="flex flex-wrap gap-2">
        {REFERENCE_LISTS.map((name) => (
          <NavLink
            key={name}
            to={`/admin/reference/${name}`}
            className={({ isActive }) =>
              `rounded-md px-3 py-1 text-sm ${isActive ? 'bg-secondary font-medium' : 'hover:bg-muted'}`
            }
          >
            {t(`reference.lists.${name}`)}
          </NavLink>
        ))}
      </nav>
      <FormMessage error={error instanceof ApiError ? error.code : null} />
      {items.isError ? (
        <ErrorState
          error={items.error}
          onRetry={() => {
            void items.refetch()
          }}
        />
      ) : null}
      {items.data ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('reference.code')}</TableHead>
              <TableHead>{t('reference.nameEn')}</TableHead>
              <TableHead>{t('reference.nameBg')}</TableHead>
              <TableHead />
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.data.map((item, index, list) => (
              <TableRow key={item.id}>
                <TableCell className="font-mono text-xs">{item.code}</TableCell>
                <TableCell>{item.name_en}</TableCell>
                <TableCell>{item.name_bg}</TableCell>
                <TableCell>
                  <Badge variant={item.is_active ? 'secondary' : 'outline'}>
                    {item.is_active ? t('reference.active') : t('reference.inactive')}
                  </Badge>
                </TableCell>
                <TableCell className="flex flex-wrap justify-end gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label={`${t('reference.moveUp')}: ${item.name_en}`}
                    disabled={index === 0 || reorder.isPending}
                    onClick={() => {
                      move(list, index, -1)
                    }}
                  >
                    ↑
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label={`${t('reference.moveDown')}: ${item.name_en}`}
                    disabled={index === list.length - 1 || reorder.isPending}
                    onClick={() => {
                      move(list, index, 1)
                    }}
                  >
                    ↓
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      update.mutate({ id: item.id, body: { is_active: !item.is_active } })
                    }}
                  >
                    {item.is_active ? t('reference.deactivate') : t('reference.activate')}
                  </Button>
                  <ConfirmButton
                    label={t('reference.delete')}
                    title={t('reference.delete')}
                    description={t('reference.confirmDelete', { name: item.name_en })}
                    variant="destructive"
                    onConfirm={() => {
                      remove.mutate(item.id)
                    }}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <Loading variant="table" />
      )}
      <AddValue list={LIST} onAdded={refresh} />
    </section>
  )
}

function AddValue({
  list: LIST,
  onAdded,
}: {
  list: ReferenceListName
  onAdded: () => Promise<unknown>
}) {
  const notify = useNotify()
  const { t } = useTranslation('admin')
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { code: '', name_en: '', name_bg: '' },
  })
  const add = useMutation({
    mutationFn: (values: Values) =>
      call(
        api.POST('/api/v1/reference/{list}', {
          params: { path: { list: LIST } },
          body: { ...values, is_active: true },
        }),
      ),
    onSuccess: async () => {
      form.reset()
      await onAdded()
      notify.success(t('reference.added'))
    },
    onError: (error) => {
      const code = applyServerErrors(error, form.setError, ['code', 'name_en', 'name_bg'])
      if (code) form.setError('root', { message: code })
    },
  })
  const errors = form.formState.errors
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('reference.add')}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          className="grid items-start gap-4 sm:grid-cols-[1fr_1fr_1fr_auto]"
          onSubmit={(event) => {
            void form.handleSubmit((values) => {
              add.mutate(values)
            })(event)
          }}
        >
          <div className="sm:col-span-4">
            <FormMessage error={errors.root?.message} />
          </div>
          <FormField
            label={t('reference.code')}
            required
            error={errors.code?.message}
            hint={t('reference.codeHint')}
          >
            {(control) => <Input {...control} {...form.register('code')} />}
          </FormField>
          <FormField label={t('reference.nameEn')} required error={errors.name_en?.message}>
            {(control) => <Input {...control} {...form.register('name_en')} />}
          </FormField>
          <FormField label={t('reference.nameBg')} required error={errors.name_bg?.message}>
            {(control) => <Input {...control} lang="bg" {...form.register('name_bg')} />}
          </FormField>
          <Button type="submit" className="mt-6" disabled={add.isPending}>
            {t('reference.add')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
