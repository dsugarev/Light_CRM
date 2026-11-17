import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

import { api, asPage, call } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { NativeSelect } from '@/components/NativeSelect'
import { Textarea } from '@/components/Textarea'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { OrganizationPicker } from '@/features/organizations/OrganizationPicker'
import { applyServerErrors } from '@/lib/errors'

import { FIELDS, schema, type OpportunityValues } from './opportunityValues'

const MONEY_INPUT = { inputMode: 'decimal' }
const DATE_INPUT = { type: 'date' }
const PERCENT_INPUT = { inputMode: 'numeric' }

interface OpportunityFormProps {
  defaultValues: OpportunityValues
  /** The organization can be chosen only when creating (API spec 10). */
  organizationFixed: boolean
  submitLabel: string
  pending: boolean
  onSubmit: (values: OpportunityValues) => Promise<unknown>
}

/** FR-OPP-01: name and organization are required; stage and probability follow the pipeline. */
export function OpportunityForm({
  defaultValues,
  organizationFixed,
  submitLabel,
  pending,
  onSubmit,
}: OpportunityFormProps) {
  const { t } = useTranslation('opportunities')
  const { t: tc } = useTranslation()
  const form = useForm<OpportunityValues>({ resolver: zodResolver(schema), defaultValues })
  const errors = form.formState.errors
  const organization = useWatch({ control: form.control, name: 'organization' })
  const contacts = useQuery({
    queryKey: ['organizations', organization?.id, 'contacts', 'picker'],
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/organizations/{org_id}/contacts', {
            params: { path: { org_id: organization?.id ?? '' }, query: { page_size: 100 } },
          }),
        ),
      ),
    enabled: organization !== null,
  })

  const text = (
    field: (typeof FIELDS)[number],
    label: string,
    extra: Record<string, unknown> = {},
    hint?: string,
  ) => (
    <FormField label={label} error={errors[field]?.message} hint={hint}>
      {(control) => <Input {...control} {...extra} {...form.register(field)} />}
    </FormField>
  )

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        void form.handleSubmit(async (values) => {
          try {
            await onSubmit(values)
          } catch (error) {
            const code = applyServerErrors(error, form.setError, [...FIELDS, 'organization'])
            if (code) form.setError('root', { message: code })
          }
        })(event)
      }}
    >
      <FormMessage error={errors.root?.message} />
      {text('name', t('fields.name'))}
      <FormField label={t('fields.organization')} error={errors.organization?.message}>
        {(control) =>
          organizationFixed ? (
            <span id={control.id} className="text-sm font-medium">
              {organization?.name}
            </span>
          ) : (
            <Controller
              control={form.control}
              name="organization"
              render={({ field }) => (
                <OrganizationPicker
                  id={control.id}
                  value={field.value}
                  onChange={(value) => {
                    field.onChange(value)
                    form.setValue('primary_contact_id', '')
                  }}
                  invalid={control['aria-invalid']}
                />
              )}
            />
          )
        }
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label={t('fields.contact')} error={errors.primary_contact_id?.message}>
          {(control) => (
            <NativeSelect
              {...control}
              disabled={organization === null}
              {...form.register('primary_contact_id')}
            >
              <option value="">{t('fields.none')}</option>
              {(contacts.data?.items ?? []).map((contact) => (
                <option key={contact.id} value={contact.id}>
                  {`${contact.first_name} ${contact.last_name}`}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        {text('amount', t('fields.amount'), MONEY_INPUT)}
        {text('expected_close_date', t('fields.expectedCloseDate'), DATE_INPUT)}
        {text('probability', t('fields.probability'), PERCENT_INPUT, t('hints.probability'))}
        {text('competitor', t('fields.competitor'))}
      </div>
      <FormField label={t('fields.nextStep')} error={errors.next_step?.message}>
        {(control) => <Textarea {...control} rows={2} {...form.register('next_step')} />}
      </FormField>
      <FormField label={t('fields.description')} error={errors.description?.message}>
        {(control) => <Textarea {...control} {...form.register('description')} />}
      </FormField>
      <Button type="submit" className="self-start" disabled={pending}>
        {pending ? tc('actions.saving') : submitLabel}
      </Button>
    </form>
  )
}
