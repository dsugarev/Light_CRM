import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { NativeSelect } from '@/components/NativeSelect'
import { Textarea } from '@/components/Textarea'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { OrganizationPicker } from '@/features/organizations/OrganizationPicker'
import { referenceName, useReferenceList } from '@/features/reference/useReferenceList'
import { applyServerErrors } from '@/lib/errors'
import { useLocale } from '@/lib/useLocale'

import { FIELDS, schema, type LeadValues } from './leadValues'

const EMAIL_INPUT = { type: 'email' }
const PHONE_INPUT = { type: 'tel' }
const MONEY_INPUT = { inputMode: 'decimal' }

interface LeadFormProps {
  defaultValues: LeadValues
  submitLabel: string
  pending: boolean
  onSubmit: (values: LeadValues) => Promise<unknown>
}

/** FR-LEAD-01: a company name is enough; everything else is optional. */
export function LeadForm({ defaultValues, submitLabel, pending, onSubmit }: LeadFormProps) {
  const { t } = useTranslation('leads')
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const sources = useReferenceList('lead-sources')
  const form = useForm<LeadValues>({ resolver: zodResolver(schema), defaultValues })
  const errors = form.formState.errors

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
            const code = applyServerErrors(error, form.setError, FIELDS)
            if (code) form.setError('root', { message: code })
          }
        })(event)
      }}
    >
      <FormMessage error={errors.root?.message} />
      {text('title', t('fields.title'))}
      <div className="grid gap-4 sm:grid-cols-2">
        {text('company_name', t('fields.companyName'), {}, t('hints.companyName'))}
        {text('contact_name', t('fields.contactName'))}
        {text('email', t('fields.email'), EMAIL_INPUT)}
        {text('phone', t('fields.phone'), PHONE_INPUT)}
        <FormField label={t('fields.source')} error={errors.source_id?.message}>
          {(control) => (
            <NativeSelect {...control} {...form.register('source_id')}>
              <option value="">{t('fields.none')}</option>
              {(sources.data ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {referenceName(item, locale)}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        {text('estimated_value', t('fields.estimatedValue'), MONEY_INPUT)}
      </div>
      <FormField
        label={t('fields.organization')}
        error={errors.organization?.message}
        hint={t('hints.organization')}
      >
        {(control) => (
          <Controller
            control={form.control}
            name="organization"
            render={({ field }) => (
              <OrganizationPicker
                id={control.id}
                value={field.value}
                onChange={field.onChange}
                invalid={control['aria-invalid']}
              />
            )}
          />
        )}
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
