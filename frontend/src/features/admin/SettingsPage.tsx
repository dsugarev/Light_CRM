import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'

import { api, call, type Schemas } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/NativeSelect'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { applyServerErrors } from '@/lib/errors'

const minutes = (min: number, max: number) =>
  z.coerce
    .number<string>({ error: 'validation.int_parsing' })
    .int({ error: 'validation.int_parsing' })
    .min(min, { error: 'validation.greater_than_equal' })
    .max(max, { error: 'validation.less_than_equal' })

const schema = z
  .object({
    session_idle_timeout_minutes: minutes(15, 1440),
    session_absolute_timeout_minutes: minutes(60, 43200),
    stale_opportunity_days: minutes(1, 365),
    mfa_required_for_admins: z.boolean(),
    ai_model: z.string().min(1),
  })
  .refine((v) => v.session_idle_timeout_minutes <= v.session_absolute_timeout_minutes, {
    path: ['session_idle_timeout_minutes'],
    error: 'validation.exceeds_absolute',
  })
type Input_ = z.input<typeof schema>
type Values = z.output<typeof schema>
const FIELDS = [
  'session_idle_timeout_minutes',
  'session_absolute_timeout_minutes',
  'stale_opportunity_days',
  'ai_model',
] as const
type AiModel = Schemas['AiModelOption']

/** FR-AUTH-04, FR-OPP-06, FR-AI-10: session timeouts, the stale threshold and the
 * assistant's model are set by an Admin. */
export function SettingsPage() {
  const { t } = useTranslation('admin')
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => call(api.GET('/api/v1/settings')),
  })
  const models = useQuery({
    queryKey: ['settings', 'ai-models'],
    queryFn: () => call(api.GET('/api/v1/settings/ai-models')),
  })
  return (
    <section className="mx-auto flex max-w-xl flex-col gap-6">
      <PageHeader title={t('settings.title')} />
      {settings.data && models.data ? (
        <SettingsForm current={settings.data} models={models.data} />
      ) : (
        <Loading variant="form" />
      )}
    </section>
  )
}

function SettingsForm({
  current,
  models,
}: {
  current: Schemas['RuntimeSettings']
  models: AiModel[]
}) {
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const queryClient = useQueryClient()
  const form = useForm<Input_, unknown, Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      session_idle_timeout_minutes: String(current.session_idle_timeout_minutes),
      session_absolute_timeout_minutes: String(current.session_absolute_timeout_minutes),
      stale_opportunity_days: String(current.stale_opportunity_days),
      mfa_required_for_admins: current.mfa_required_for_admins,
      ai_model: current.ai_model,
    },
  })
  const save = useMutation({
    mutationFn: (values: Values) => call(api.PATCH('/api/v1/settings', { body: values })),
    onSuccess: (updated) => {
      queryClient.setQueryData(['settings'], updated)
    },
    onError: (error) => applyServerErrors(error, form.setError, FIELDS),
  })
  const errors = form.formState.errors
  const aiModel = useWatch({ control: form.control, name: 'ai_model' })
  const chosen = models.find((model) => model.id === aiModel)
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.sessions')}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            void form.handleSubmit((values) => {
              save.mutate(values)
            })(event)
          }}
        >
          <FormMessage success={save.isSuccess ? tc('states.saved') : null} />
          <FormField
            label={t('settings.idle')}
            required
            error={errors.session_idle_timeout_minutes?.message}
            hint={t('settings.idleHint')}
          >
            {(control) => (
              <Input
                {...control}
                inputMode="numeric"
                {...form.register('session_idle_timeout_minutes')}
              />
            )}
          </FormField>
          <FormField
            label={t('settings.absolute')}
            required
            error={errors.session_absolute_timeout_minutes?.message}
            hint={t('settings.absoluteHint')}
          >
            {(control) => (
              <Input
                {...control}
                inputMode="numeric"
                {...form.register('session_absolute_timeout_minutes')}
              />
            )}
          </FormField>
          <h3 className="pt-2 font-medium">{t('settings.opportunities')}</h3>
          <FormField
            label={t('settings.staleDays')}
            required
            error={errors.stale_opportunity_days?.message}
            hint={t('settings.staleDaysHint')}
          >
            {(control) => (
              <Input
                {...control}
                inputMode="numeric"
                {...form.register('stale_opportunity_days')}
              />
            )}
          </FormField>
          <h3 className="pt-2 font-medium">{t('settings.security')}</h3>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" {...form.register('mfa_required_for_admins')} />
            <span>
              {t('settings.mfaRequired')}
              <span className="block text-muted-foreground">{t('settings.mfaRequiredHint')}</span>
            </span>
          </label>
          {models.length > 0 ? (
            <>
              <h3 className="pt-2 font-medium">{t('settings.assistant')}</h3>
              <FormField
                label={t('settings.aiModel')}
                required
                error={errors.ai_model?.message}
                hint={t('settings.aiModelHint')}
              >
                {(control) => (
                  <NativeSelect {...control} {...form.register('ai_model')}>
                    {models.map((model) => (
                      <option key={model.id} value={model.id} disabled={!model.available}>
                        {model.available
                          ? model.label
                          : t('settings.aiModelNoKey', { label: model.label })}
                      </option>
                    ))}
                  </NativeSelect>
                )}
              </FormField>
              {chosen?.data_note === 'may_keep_prompts' ? (
                <p
                  role="note"
                  className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-foreground dark:bg-warning/20"
                >
                  {t('settings.aiModelDataNote')}
                </p>
              ) : null}
            </>
          ) : null}
          <Button type="submit" className="self-start" disabled={save.isPending}>
            {save.isPending ? tc('actions.saving') : tc('actions.save')}
          </Button>
          <UnsavedChangesGuard
            when={
              form.formState.isDirty &&
              !form.formState.isSubmitting &&
              !form.formState.isSubmitSuccessful
            }
          />
        </form>
      </CardContent>
    </Card>
  )
}
