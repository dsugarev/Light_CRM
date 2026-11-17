import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
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
  })
  .refine((v) => v.session_idle_timeout_minutes <= v.session_absolute_timeout_minutes, {
    path: ['session_idle_timeout_minutes'],
    error: 'validation.exceeds_absolute',
  })
type Input_ = z.input<typeof schema>
type Values = z.output<typeof schema>
const FIELDS = ['session_idle_timeout_minutes', 'session_absolute_timeout_minutes'] as const

/** FR-AUTH-04: session timeouts are configurable by an Admin. */
export function SettingsPage() {
  const { t } = useTranslation('admin')
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => call(api.GET('/api/v1/settings')),
  })
  return (
    <section className="mx-auto flex max-w-xl flex-col gap-6">
      <PageHeader title={t('settings.title')} />
      {settings.data ? <SettingsForm current={settings.data} /> : <Loading />}
    </section>
  )
}

function SettingsForm({ current }: { current: Schemas['RuntimeSettings'] }) {
  const { t } = useTranslation('admin')
  const { t: tc } = useTranslation()
  const queryClient = useQueryClient()
  const form = useForm<Input_, unknown, Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      session_idle_timeout_minutes: String(current.session_idle_timeout_minutes),
      session_absolute_timeout_minutes: String(current.session_absolute_timeout_minutes),
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
          <Button type="submit" className="self-start" disabled={save.isPending}>
            {save.isPending ? tc('actions.saving') : tc('actions.save')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
