import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

import { ApiError, type Schemas } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { NativeSelect } from '@/components/NativeSelect'
import { Textarea } from '@/components/Textarea'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DuplicateMatches } from '@/features/organizations/DuplicateMatches'
import { OrganizationPicker } from '@/features/organizations/OrganizationPicker'
import { SUPPORTED_LOCALES } from '@/i18n'
import { applyServerErrors } from '@/lib/errors'

import { FIELDS, schema, type ContactValues } from './contactValues'

type Match = Schemas['Match']
const OFF = { autoComplete: 'off' }
const EMAIL_INPUT = { type: 'email' }
const PHONE_INPUT = { type: 'tel' }

interface ContactFormProps {
  defaultValues: ContactValues
  submitLabel: string
  pending: boolean
  isEdit: boolean
  onSubmit: (values: ContactValues, confirmDuplicate: boolean) => Promise<unknown>
}

export function ContactForm({
  defaultValues,
  submitLabel,
  pending,
  isEdit,
  onSubmit,
}: ContactFormProps) {
  const { t } = useTranslation('party')
  const { t: tc } = useTranslation()
  const form = useForm<ContactValues>({ resolver: zodResolver(schema), defaultValues })
  const [conflict, setConflict] = useState<Match[] | null>(null)
  const errors = form.formState.errors

  const submit = (confirmDuplicate: boolean) =>
    form.handleSubmit(async (values) => {
      try {
        await onSubmit(values, confirmDuplicate)
      } catch (error) {
        if (error instanceof ApiError && error.code === 'conflict.duplicate') {
          setConflict((error.problem['matches'] as Match[] | undefined) ?? [])
          return
        }
        if (error instanceof ApiError) {
          const orgError = error.errors.find((e) => e.field === 'organization_id')
          if (orgError) form.setError('organization', { message: orgError.code })
        }
        const code = applyServerErrors(error, form.setError, FIELDS)
        if (code && !form.formState.errors.organization) form.setError('root', { message: code })
      }
    })

  const text = (
    field: (typeof FIELDS)[number],
    label: string,
    extra: Record<string, unknown> = {},
  ) => (
    <FormField label={label} error={errors[field]?.message}>
      {(control) => <Input {...control} {...extra} {...form.register(field)} />}
    </FormField>
  )

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        void submit(false)(event)
      }}
    >
      <FormMessage error={errors.root?.message} />
      {conflict ? (
        <DuplicateMatches matches={conflict} kind="contact">
          <Button
            type="button"
            variant="outline"
            className="self-start"
            disabled={pending}
            onClick={() => {
              void submit(true)()
            }}
          >
            {isEdit ? t('duplicates.saveAnywayChanges') : t('duplicates.saveAnyway')}
          </Button>
        </DuplicateMatches>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {text('first_name', t('contact.fields.firstName'), OFF)}
        {text('last_name', t('contact.fields.lastName'), OFF)}
        {text('job_title', t('contact.fields.jobTitle'))}
        {text('email', t('contact.fields.email'), EMAIL_INPUT)}
        {text('phone', t('contact.fields.phone'), PHONE_INPUT)}
        <FormField
          label={t('contact.fields.preferredLocale')}
          error={errors.preferred_locale?.message}
        >
          {(control) => (
            <NativeSelect {...control} {...form.register('preferred_locale')}>
              <option value="">{t('contact.notSet')}</option>
              {SUPPORTED_LOCALES.map((locale) => (
                <option key={locale} value={locale}>
                  {tc(`language.${locale}`)}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
      </div>
      <FormField label={t('contact.fields.organization')} error={errors.organization?.message}>
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
      <FormField label={t('contact.fields.notes')} error={errors.notes?.message}>
        {(control) => <Textarea {...control} {...form.register('notes')} />}
      </FormField>
      <Button type="submit" className="self-start" disabled={pending}>
        {pending ? tc('actions.saving') : submitLabel}
      </Button>
    </form>
  )
}
