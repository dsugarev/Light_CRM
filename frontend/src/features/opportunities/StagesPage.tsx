import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'

import { api, ApiError, call } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { applyServerErrors } from '@/lib/errors'
import { useNotify } from '@/lib/notify'

import { STAGE_TYPES, type Stage } from './opportunityValues'
import { usePipeline } from './usePipeline'

const name = z
  .string()
  .trim()
  .min(1, { error: 'validation.required' })
  .max(100, { error: 'validation.string_too_long' })
const probability = z.coerce
  .number<string>({ error: 'validation.int_parsing' })
  .int({ error: 'validation.int_parsing' })
  .min(0, { error: 'validation.greater_than_equal' })
  .max(100, { error: 'validation.less_than_equal' })
const schema = z.object({
  name_en: name,
  name_bg: name,
  default_probability: probability,
  stage_type: z.enum(STAGE_TYPES),
})
type Input_ = z.input<typeof schema>
type Values = z.output<typeof schema>
const FIELDS = ['name_en', 'name_bg', 'default_probability', 'stage_type'] as const

/** FR-OPP-02 / FR-ADM-02: Admins configure the pipeline's stages. */
export function StagesPage() {
  const notify = useNotify()
  const { t } = useTranslation('opportunities')
  const pipeline = usePipeline()
  const queryClient = useQueryClient()
  const pipelineId = pipeline.data?.id ?? ''
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['pipelines'] })
  const stagePath = (stageId: string) => ({
    params: { path: { pipeline_id: pipelineId, stage_id: stageId } },
  })

  const update = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string
      body: {
        is_active?: boolean
        name_en?: string
        name_bg?: string
        default_probability?: number
      }
    }) =>
      call(
        api.PATCH('/api/v1/pipelines/{pipeline_id}/stages/{stage_id}', { ...stagePath(id), body }),
      ),
    onSuccess: async () => {
      await refresh()
      notify.success(t('stages.saved'))
    },
  })
  const reorder = useMutation({
    mutationFn: (ids: string[]) =>
      call(
        api.PUT('/api/v1/pipelines/{pipeline_id}/stages/order', {
          params: { path: { pipeline_id: pipelineId } },
          body: ids,
        }),
      ),
    onSuccess: refresh,
  })
  const remove = useMutation({
    mutationFn: (id: string) =>
      call(api.DELETE('/api/v1/pipelines/{pipeline_id}/stages/{stage_id}', stagePath(id))),
    onSuccess: async () => {
      await refresh()
      notify.success(t('stages.deleted'))
    },
  })
  const move = (stages: Stage[], index: number, delta: number) => {
    const ids = stages.map((s) => s.id)
    const [moved] = ids.splice(index, 1)
    if (moved) ids.splice(index + delta, 0, moved)
    reorder.mutate(ids)
  }
  const error = [update.error, reorder.error, remove.error].find((e) => e instanceof ApiError)

  return (
    <section className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader title={t('stages.title')} />
      <p className="text-sm text-muted-foreground">{t('stages.help')}</p>
      <FormMessage error={error instanceof ApiError ? error.code : null} />
      {pipeline.isError ? (
        <ErrorState
          error={pipeline.error}
          onRetry={() => {
            void pipeline.refetch()
          }}
        />
      ) : null}
      {pipeline.data ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('stages.nameEn')}</TableHead>
              <TableHead>{t('stages.nameBg')}</TableHead>
              <TableHead>{t('stages.probability')}</TableHead>
              <TableHead>{t('stages.type')}</TableHead>
              <TableHead />
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pipeline.data.stages.map((stage, index, stages) => (
              <StageRow
                key={`${stage.id}-${stage.name_en}-${stage.name_bg}-${String(stage.default_probability)}`}
                stage={stage}
                first={index === 0}
                last={index === stages.length - 1}
                busy={reorder.isPending || update.isPending}
                onMove={(delta) => {
                  move(stages, index, delta)
                }}
                onSave={(body) => {
                  update.mutate({ id: stage.id, body })
                }}
                onDelete={() => {
                  remove.mutate(stage.id)
                }}
              />
            ))}
          </TableBody>
        </Table>
      ) : (
        <Loading variant="table" />
      )}
      {pipeline.data ? <AddStage pipelineId={pipeline.data.id} onAdded={refresh} /> : null}
    </section>
  )
}

function StageRow({
  stage,
  first,
  last,
  busy,
  onMove,
  onSave,
  onDelete,
}: {
  stage: Stage
  first: boolean
  last: boolean
  busy: boolean
  onMove: (delta: number) => void
  onSave: (body: {
    is_active?: boolean
    name_en?: string
    name_bg?: string
    default_probability?: number
  }) => void
  onDelete: () => void
}) {
  const { t } = useTranslation('opportunities')
  const [draft, setDraft] = useState({
    name_en: stage.name_en,
    name_bg: stage.name_bg,
    default_probability: String(stage.default_probability),
  })
  const probability = Number(draft.default_probability)
  const valid =
    draft.name_en.trim() !== '' &&
    draft.name_bg.trim() !== '' &&
    /^\d{1,3}$/.test(draft.default_probability) &&
    probability <= 100
  const changed =
    draft.name_en !== stage.name_en ||
    draft.name_bg !== stage.name_bg ||
    probability !== stage.default_probability
  return (
    <TableRow>
      <TableCell>
        <Input
          aria-label={`${t('stages.nameEn')}: ${stage.name_en}`}
          value={draft.name_en}
          maxLength={100}
          onChange={(e) => {
            setDraft((d) => ({ ...d, name_en: e.target.value }))
          }}
        />
      </TableCell>
      <TableCell>
        <Input
          aria-label={`${t('stages.nameBg')}: ${stage.name_en}`}
          lang="bg"
          value={draft.name_bg}
          maxLength={100}
          onChange={(e) => {
            setDraft((d) => ({ ...d, name_bg: e.target.value }))
          }}
        />
      </TableCell>
      <TableCell>
        <Input
          aria-label={`${t('stages.probability')}: ${stage.name_en}`}
          inputMode="numeric"
          className="w-20"
          value={draft.default_probability}
          onChange={(e) => {
            setDraft((d) => ({ ...d, default_probability: e.target.value }))
          }}
        />
      </TableCell>
      <TableCell>
        <span className="flex flex-col items-start gap-1">
          <span>{t(`stageType.${stage.stage_type}`)}</span>
          {stage.is_active ? null : <Badge variant="outline">{t('stages.inactive')}</Badge>}
        </span>
      </TableCell>
      <TableCell>
        <Button
          type="button"
          size="sm"
          disabled={!changed || !valid || busy}
          onClick={() => {
            onSave({
              name_en: draft.name_en.trim(),
              name_bg: draft.name_bg.trim(),
              default_probability: probability,
            })
          }}
        >
          {t('stages.save')}
        </Button>
      </TableCell>
      <TableCell className="flex flex-wrap justify-end gap-1">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label={`${t('stages.moveUp')}: ${stage.name_en}`}
          disabled={first || busy}
          onClick={() => {
            onMove(-1)
          }}
        >
          ↑
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label={`${t('stages.moveDown')}: ${stage.name_en}`}
          disabled={last || busy}
          onClick={() => {
            onMove(1)
          }}
        >
          ↓
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => {
            onSave({ is_active: !stage.is_active })
          }}
        >
          {stage.is_active ? t('stages.deactivate') : t('stages.activate')}
        </Button>
        <ConfirmButton
          label={t('stages.delete')}
          title={t('stages.delete')}
          description={t('stages.confirmDelete', { name: stage.name_en })}
          variant="destructive"
          onConfirm={onDelete}
        />
      </TableCell>
    </TableRow>
  )
}

function AddStage({
  pipelineId,
  onAdded,
}: {
  pipelineId: string
  onAdded: () => Promise<unknown>
}) {
  const notify = useNotify()
  const { t } = useTranslation('opportunities')
  const form = useForm<Input_, unknown, Values>({
    resolver: zodResolver(schema),
    defaultValues: { name_en: '', name_bg: '', default_probability: '', stage_type: 'open' },
  })
  const add = useMutation({
    mutationFn: (values: Values) =>
      call(
        api.POST('/api/v1/pipelines/{pipeline_id}/stages', {
          params: { path: { pipeline_id: pipelineId } },
          body: values,
        }),
      ),
    onSuccess: async () => {
      form.reset()
      await onAdded()
      notify.success(t('stages.added'))
    },
    onError: (error) => {
      const code = applyServerErrors(error, form.setError, FIELDS)
      if (code) form.setError('root', { message: code })
    },
  })
  const errors = form.formState.errors
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('stages.add')}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          className="grid items-start gap-4 sm:grid-cols-[1fr_1fr_8rem_10rem_auto]"
          onSubmit={(event) => {
            void form.handleSubmit((values) => {
              add.mutate(values)
            })(event)
          }}
        >
          <div className="sm:col-span-5">
            <FormMessage error={errors.root?.message} />
          </div>
          <FormField label={t('stages.nameEn')} required error={errors.name_en?.message}>
            {(control) => <Input {...control} {...form.register('name_en')} />}
          </FormField>
          <FormField label={t('stages.nameBg')} required error={errors.name_bg?.message}>
            {(control) => <Input {...control} lang="bg" {...form.register('name_bg')} />}
          </FormField>
          <FormField
            label={t('stages.probability')}
            required
            error={errors.default_probability?.message}
          >
            {(control) => (
              <Input {...control} inputMode="numeric" {...form.register('default_probability')} />
            )}
          </FormField>
          <FormField label={t('stages.type')} required error={errors.stage_type?.message}>
            {(control) => (
              <NativeSelect {...control} {...form.register('stage_type')}>
                {STAGE_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {t(`stageType.${type}`)}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <Button type="submit" className="mt-6" disabled={add.isPending}>
            {t('stages.add')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
