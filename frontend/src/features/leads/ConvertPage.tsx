import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { api, ApiError, call, type Schemas } from '@/api/client'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { FormMessage } from '@/components/FormMessage'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { stageName } from '@/features/opportunities/opportunityValues'
import { usePipeline } from '@/features/opportunities/usePipeline'
import { useLocale } from '@/lib/useLocale'

type Preview = Schemas['ConversionPreview']
type Match = Schemas['Match']
const NEW = 'new'
const NONE = 'none'
const ORGANIZATION_GROUP = 'organization'
const CONTACT_GROUP = 'contact'
const CONTACT_FIELDS = ['first_name', 'last_name', 'email'] as const
const CONTACT_LINK_FIELD = 'contact.existing_id'

interface ChoiceProps {
  group: string
  value: string
  label: string
  current: string
  onChoose: (value: string) => void
}

function Choice({ group, value, label, current, onChoose }: ChoiceProps) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="radio"
        name={group}
        value={value}
        checked={current === value}
        onChange={() => {
          onChoose(value)
        }}
      />
      {label}
    </label>
  )
}

/** FR-LEAD-04: choose or create the organization and contact, then create the opportunity. */
export function ConvertPage() {
  const { leadId = '' } = useParams()
  const path = { params: { path: { lead_id: leadId } } }
  const lead = useQuery({
    queryKey: ['leads', leadId],
    queryFn: () => call(api.GET('/api/v1/leads/{lead_id}', path)),
  })
  const preview = useQuery({
    queryKey: ['leads', leadId, 'conversion-preview'],
    queryFn: () => call(api.GET('/api/v1/leads/{lead_id}/conversion-preview', path)),
  })
  if (lead.isError) return <ErrorState error={lead.error} />
  if (preview.isError) return <ErrorState error={preview.error} />
  if (!lead.data || !preview.data) return <Loading />
  return <ConvertForm lead={lead.data} preview={preview.data} />
}

function defaultChoice(linked: { id: string } | null, matches: Match[], fallback: string) {
  return linked?.id ?? matches[0]?.id ?? fallback
}

function ConvertForm({ lead, preview }: { lead: Schemas['LeadOut']; preview: Preview }) {
  const { t } = useTranslation('leads')
  const locale = useLocale()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const pipeline = usePipeline()
  const openStages = (pipeline.data?.stages ?? []).filter(
    (s) => s.is_active && s.stage_type === 'open',
  )
  const org = preview.organization
  const person = preview.contact
  const [orgChoice, setOrgChoice] = useState(defaultChoice(org.linked, org.matches, NEW))
  const [orgName, setOrgName] = useState(org.suggested.name)
  const [contactChoice, setContactChoice] = useState(
    defaultChoice(person.linked, person.matches, person.suggested ? NEW : NONE),
  )
  const [contact, setContact] = useState({
    first_name: person.suggested?.first_name ?? '',
    last_name: person.suggested?.last_name ?? '',
    email: person.suggested?.email ?? '',
  })
  const [opportunity, setOpportunity] = useState({
    name: preview.opportunity.name,
    amount: preview.opportunity.amount ?? '',
    expected_close_date: '',
    stage_id: preview.opportunity.stage.id,
  })
  const [confirmDuplicate, setConfirmDuplicate] = useState(false)
  const [duplicates, setDuplicates] = useState<Match[]>([])

  const convert = useMutation({
    mutationFn: () =>
      call(
        api.POST('/api/v1/leads/{lead_id}/convert', {
          params: { path: { lead_id: lead.id } },
          body: {
            version: lead.version,
            organization:
              orgChoice === NEW
                ? {
                    new: {
                      name: orgName.trim(),
                      country: 'BG',
                      confirm_duplicate: confirmDuplicate,
                    },
                  }
                : { existing_id: orgChoice },
            contact:
              contactChoice === NONE
                ? null
                : contactChoice === NEW
                  ? {
                      new: {
                        first_name: contact.first_name.trim(),
                        last_name: contact.last_name.trim(),
                        email: contact.email.trim() || null,
                        confirm_duplicate: confirmDuplicate,
                      },
                    }
                  : { existing_id: contactChoice },
            opportunity: {
              name: opportunity.name.trim(),
              amount: opportunity.amount ? opportunity.amount.replace(',', '.') : null,
              expected_close_date: opportunity.expected_close_date || null,
              stage_id: opportunity.stage_id,
            },
          },
        }),
      ),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['leads'] })
      await queryClient.invalidateQueries({ queryKey: ['opportunities'] })
      await queryClient.invalidateQueries({ queryKey: ['organizations'] })
      toast.success(t('convert.done'))
      await navigate(`/opportunities/${result.opportunity.id}`)
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'conflict.duplicate') {
        setDuplicates((error.problem['matches'] as Match[] | undefined) ?? [])
      }
    },
  })
  const error = convert.error instanceof ApiError ? convert.error : null
  const fieldError = (field: string) => error?.errors.find((e) => e.field.startsWith(field))?.code

  const matchLabel = (m: Match) =>
    `${m.name}${m.city ? `, ${m.city}` : ''}${m.email ? ` <${m.email}>` : ''} — ${t(`convert.reason.${m.reason}`)}`
  const contactLinkError = fieldError(CONTACT_LINK_FIELD)
  const orgOptions = [
    ...(org.linked
      ? [{ value: org.linked.id, label: t('convert.linked', { name: org.linked.name }) }]
      : []),
    ...org.matches
      .filter((m) => m.id !== org.linked?.id && !m.archived)
      .map((m) => ({ value: m.id, label: matchLabel(m) })),
    { value: NEW, label: t('convert.newOrganization') },
  ]
  const contactOptions = [
    ...(person.linked
      ? [{ value: person.linked.id, label: t('convert.linked', { name: person.linked.name }) }]
      : []),
    ...person.matches
      .filter((m) => m.id !== person.linked?.id && !m.archived)
      .map((m) => ({ value: m.id, label: matchLabel(m) })),
    { value: NEW, label: t('convert.newContact') },
    { value: NONE, label: t('convert.noContact') },
  ]

  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader title={t('convert.title', { title: lead.title })} />
      <form
        aria-label={t('convert.formLabel')}
        className="flex flex-col gap-6"
        onSubmit={(event) => {
          event.preventDefault()
          convert.mutate()
        }}
      >
        <FormMessage
          error={error?.errors.length === 0 && duplicates.length === 0 ? error.code : null}
        />
        <Card>
          <CardHeader>
            <CardTitle>{t('convert.organization')}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <fieldset className="flex flex-col gap-2" aria-label={t('convert.organization')}>
              {orgOptions.map((option) => (
                <Choice
                  key={option.value}
                  group={ORGANIZATION_GROUP}
                  {...option}
                  current={orgChoice}
                  onChoose={setOrgChoice}
                />
              ))}
            </fieldset>
            {orgChoice === NEW ? (
              <FormField label={t('convert.organizationName')} error={fieldError('organization')}>
                {(control) => (
                  <Input
                    {...control}
                    value={orgName}
                    maxLength={200}
                    onChange={(e) => {
                      setOrgName(e.target.value)
                    }}
                  />
                )}
              </FormField>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('convert.contact')}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <fieldset className="flex flex-col gap-2" aria-label={t('convert.contact')}>
              {contactOptions.map((option) => (
                <Choice
                  key={option.value}
                  group={CONTACT_GROUP}
                  {...option}
                  current={contactChoice}
                  onChoose={setContactChoice}
                />
              ))}
            </fieldset>
            {contactChoice === NEW ? (
              <div className="grid gap-3 sm:grid-cols-3">
                {CONTACT_FIELDS.map((field) => (
                  <FormField
                    key={field}
                    label={t(`convert.${field}`)}
                    error={error?.errors.find((e) => e.field === `contact.new.${field}`)?.code}
                  >
                    {(control) => (
                      <Input
                        {...control}
                        value={contact[field]}
                        onChange={(e) => {
                          setContact((c) => ({ ...c, [field]: e.target.value }))
                        }}
                      />
                    )}
                  </FormField>
                ))}
              </div>
            ) : null}
            {contactLinkError ? <FormMessage error={contactLinkError} /> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('convert.opportunity')}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <FormField label={t('convert.opportunityName')} error={fieldError('opportunity.name')}>
              {(control) => (
                <Input
                  {...control}
                  value={opportunity.name}
                  maxLength={200}
                  onChange={(e) => {
                    setOpportunity((o) => ({ ...o, name: e.target.value }))
                  }}
                />
              )}
            </FormField>
            <FormField label={t('convert.amount')} error={fieldError('opportunity.amount')}>
              {(control) => (
                <Input
                  {...control}
                  inputMode="decimal"
                  value={opportunity.amount}
                  onChange={(e) => {
                    setOpportunity((o) => ({ ...o, amount: e.target.value }))
                  }}
                />
              )}
            </FormField>
            <FormField label={t('convert.expectedClose')}>
              {(control) => (
                <Input
                  {...control}
                  type="date"
                  value={opportunity.expected_close_date}
                  onChange={(e) => {
                    setOpportunity((o) => ({ ...o, expected_close_date: e.target.value }))
                  }}
                />
              )}
            </FormField>
            <FormField label={t('convert.stage')} error={fieldError('stage_id')}>
              {(control) => (
                <NativeSelect
                  {...control}
                  value={opportunity.stage_id}
                  onChange={(e) => {
                    setOpportunity((o) => ({ ...o, stage_id: e.target.value }))
                  }}
                >
                  {(openStages.length > 0 ? openStages : [preview.opportunity.stage]).map((s) => (
                    <option key={s.id} value={s.id}>
                      {stageName(s, locale)}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
          </CardContent>
        </Card>
        {duplicates.length > 0 ? (
          <div
            className="flex flex-col gap-2 rounded-lg border border-destructive/50 p-4 text-sm"
            role="alert"
          >
            <p>{t('convert.duplicates')}</p>
            <ul className="list-disc pl-5">
              {duplicates.map((m) => (
                <li key={m.id}>{matchLabel(m)}</li>
              ))}
            </ul>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={confirmDuplicate}
                onChange={(e) => {
                  setConfirmDuplicate(e.target.checked)
                }}
              />
              {t('convert.confirmDuplicate')}
            </label>
          </div>
        ) : null}
        <Button type="submit" className="self-start" disabled={convert.isPending}>
          {t('convert.submit')}
        </Button>
      </form>
    </section>
  )
}
