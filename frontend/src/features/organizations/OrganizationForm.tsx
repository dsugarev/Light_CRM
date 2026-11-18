import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

import { api, ApiError, call, type Schemas } from '@/api/client'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { NativeSelect } from '@/components/NativeSelect'
import { Textarea } from '@/components/Textarea'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { useMe } from '@/features/auth/useMe'
import { useUserLookup } from '@/features/auth/useUserLookup'
import { referenceName, useReferenceList } from '@/features/reference/useReferenceList'
import { applyServerErrors } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { useLocale } from '@/lib/useLocale'

import { DuplicateMatches } from './DuplicateMatches'
import {
  FIELDS,
  organizationDefaults,
  schema,
  SIZE_BANDS,
  type OrganizationValues,
} from './organizationValues'

type Organization = Schemas['OrganizationOut']
type Match = Schemas['Match']
const NUMERIC = { inputMode: 'numeric' }
const URL_INPUT = { type: 'url' }
const COUNTRY_INPUT = { maxLength: 2 }

interface OrganizationFormProps {
  organization?: Organization
  submitLabel: string
  pending: boolean
  onSubmit: (values: OrganizationValues, confirmDuplicate: boolean) => Promise<unknown>
}

// UX-11: the fields the schema requires, marked in the form.
const REQUIRED = new Set<keyof OrganizationValues>(['name'])

/** Create/edit form with a live duplicate warning before saving (FR-PARTY-01 AC1). */
export function OrganizationForm({
  organization,
  submitLabel,
  pending,
  onSubmit,
}: OrganizationFormProps) {
  const { t } = useTranslation('party')
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const can = useCan()
  const { data: me } = useMe()
  const canReassign = can('records.reassign')
  const industries = useReferenceList('industries')
  const users = useUserLookup(canReassign)
  const form = useForm<OrganizationValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      ...organizationDefaults(organization),
      owner_id: organization?.owner.id ?? me?.id ?? '',
    },
  })
  const [conflict, setConflict] = useState<Match[] | null>(null)

  // Live duplicate check on the identifying fields, debounced.
  const [name, registration] = useWatch({
    control: form.control,
    name: ['name', 'registration_number'],
  })
  const [probe, setProbe] = useState({ name: '', registration: '' })
  useEffect(() => {
    const timer = setTimeout(() => {
      setProbe({ name: name.trim(), registration: registration.replace(/\s/g, '') })
    }, 400)
    return () => {
      clearTimeout(timer)
    }
  }, [name, registration])
  const changedIdentity =
    probe.name !== (organization?.name ?? '') ||
    probe.registration !== (organization?.registration_number ?? '')
  const duplicates = useQuery({
    queryKey: ['organizations', 'duplicate-check', probe],
    queryFn: () =>
      call(
        api.GET('/api/v1/organizations/duplicate-check', {
          params: {
            query: {
              ...(probe.name.length >= 2 ? { name: probe.name } : {}),
              ...(/^\d{9}(\d{4})?$/.test(probe.registration)
                ? { registration_number: probe.registration }
                : {}),
            },
          },
        }),
      ),
    enabled:
      changedIdentity && (probe.name.length >= 2 || /^\d{9}(\d{4})?$/.test(probe.registration)),
  })
  const liveMatches = (duplicates.data?.matches ?? []).filter((m) => m.id !== organization?.id)

  const submit = (confirmDuplicate: boolean) =>
    form.handleSubmit(async (values) => {
      try {
        await onSubmit(values, confirmDuplicate)
      } catch (error) {
        if (error instanceof ApiError && error.code === 'conflict.duplicate') {
          setConflict((error.problem['matches'] as Match[] | undefined) ?? [])
          return
        }
        const code = applyServerErrors(error, form.setError, FIELDS)
        if (code) form.setError('root', { message: code })
      }
    })

  const errors = form.formState.errors
  const text = (
    field: keyof OrganizationValues,
    label: string,
    extra: Record<string, unknown> = {},
    hint?: string,
  ) => (
    <FormField
      label={label}
      error={errors[field]?.message}
      hint={hint}
      required={REQUIRED.has(field)}
    >
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
        <DuplicateMatches matches={conflict} kind="organization">
          <Button
            type="button"
            variant="outline"
            className="self-start"
            disabled={pending}
            onClick={() => {
              void submit(true)()
            }}
          >
            {organization ? t('duplicates.saveAnywayChanges') : t('duplicates.saveAnyway')}
          </Button>
        </DuplicateMatches>
      ) : (
        <DuplicateMatches matches={liveMatches} kind="organization" />
      )}
      {text('name', t('organization.fields.name'))}
      <div className="grid gap-4 sm:grid-cols-2">
        {text(
          'registration_number',
          t('organization.fields.registrationNumber'),
          NUMERIC,
          t('organization.hints.registrationNumber'),
        )}
        {text(
          'vat_number',
          t('organization.fields.vatNumber'),
          {},
          t('organization.hints.vatNumber'),
        )}
        <FormField label={t('organization.fields.industry')} error={errors.industry_id?.message}>
          {(control) => (
            <NativeSelect {...control} {...form.register('industry_id')}>
              <option value="">{t('organization.none')}</option>
              {(industries.data ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {referenceName(item, locale)}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        <FormField label={t('organization.fields.sizeBand')} error={errors.size_band?.message}>
          {(control) => (
            <NativeSelect {...control} {...form.register('size_band')}>
              <option value="">{t('organization.none')}</option>
              {SIZE_BANDS.map((band) => (
                <option key={band} value={band}>
                  {t(`organization.sizeBands.${band}`)}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
        {text(
          'website',
          t('organization.fields.website'),
          URL_INPUT,
          t('organization.hints.website'),
        )}
        {text('address_line', t('organization.fields.addressLine'))}
        {text('postal_code', t('organization.fields.postalCode'))}
        {text('city', t('organization.fields.city'))}
        {text(
          'country',
          t('organization.fields.country'),
          COUNTRY_INPUT,
          t('organization.hints.country'),
        )}
        {canReassign ? (
          <FormField label={t('organization.fields.owner')} error={errors.owner_id?.message}>
            {(control) => (
              <NativeSelect {...control} {...form.register('owner_id')}>
                {(users.data?.items ?? []).map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.full_name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        ) : null}
      </div>
      <FormField label={t('organization.fields.notes')} error={errors.notes?.message}>
        {(control) => <Textarea {...control} {...form.register('notes')} />}
      </FormField>
      <Button type="submit" className="self-start" disabled={pending}>
        {pending ? tc('actions.saving') : submitLabel}
      </Button>
      <UnsavedChangesGuard
        when={
          form.formState.isDirty &&
          !form.formState.isSubmitting &&
          !form.formState.isSubmitSuccessful
        }
      />
    </form>
  )
}
