import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { api, call } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorState } from '@/components/ErrorState'
import { FormField } from '@/components/FormField'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Textarea } from '@/components/Textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { AssignControl } from '@/features/auth/AssignControl'
import { useMe } from '@/features/auth/useMe'
import { useCanEditOwned } from '@/features/auth/useOwnership'
import { referenceName, useReferenceList } from '@/features/reference/useReferenceList'
import { formatDate, formatMoney } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useLocale } from '@/lib/useLocale'

import { LeadStatusBadge } from './LeadStatusBadge'
import { BANT_ITEMS, BANT_STATUSES, type Lead } from './leadValues'
import { useLeadMutation } from './useLeadMutation'

type BantItem = (typeof BANT_ITEMS)[number]
type BantStatus = (typeof BANT_STATUSES)[number]
const POINTS: Record<BantStatus, number> = { yes: 25, partial: 12.5, no: 0, unknown: 0 }

export function LeadPage() {
  const { leadId = '' } = useParams()
  const { t } = useTranslation('leads')
  const locale = useLocale()
  const path = { params: { path: { lead_id: leadId } } }
  const lead = useQuery({
    queryKey: ['leads', leadId],
    queryFn: () => call(api.GET('/api/v1/leads/{lead_id}', path)),
  })
  if (lead.isError) return <ErrorState error={lead.error} />
  if (!lead.data) return <Loading />
  const l = lead.data
  const rows: [string, React.ReactNode][] = [
    [t('fields.companyName'), l.company_name],
    [t('fields.contactName'), l.contact_name],
    [
      t('fields.email'),
      l.email ? (
        <a className="hover:underline" href={`mailto:${l.email}`}>
          {l.email}
        </a>
      ) : null,
    ],
    [t('fields.phone'), l.phone],
    [t('fields.source'), l.source ? referenceName(l.source, locale) : null],
    [t('fields.estimatedValue'), l.estimated_value ? formatMoney(l.estimated_value, locale) : null],
    [
      t('fields.organization'),
      l.organization ? (
        <Link className="hover:underline" to={`/organizations/${l.organization.id}`}>
          {l.organization.name}
        </Link>
      ) : null,
    ],
    [
      t('fields.contact'),
      l.contact ? (
        <Link className="hover:underline" to={`/contacts/${l.contact.id}`}>
          {l.contact.name}
        </Link>
      ) : null,
    ],
    [t('fields.owner'), l.owner.full_name],
  ]
  return (
    <section className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader title={l.title} actions={<LeadStatusBadge status={l.status} />} />
      <LeadActions lead={l} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t('detail.details')}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
              {rows.map(([label, value]) => (
                <div key={label} className="contents">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd>{value ?? t('fields.none')}</dd>
                </div>
              ))}
            </dl>
            {l.description ? (
              <p className="mt-4 whitespace-pre-wrap text-sm">{l.description}</p>
            ) : null}
            <p className="mt-4 text-xs text-muted-foreground">
              {t('detail.createdBy', {
                name: l.created_by?.full_name ?? '',
                date: formatDate(l.created_at, locale),
              })}
            </p>
          </CardContent>
        </Card>
        <BantCard key={`${l.id}-${String(l.version)}`} lead={l} />
      </div>
    </section>
  )
}

function LeadActions({ lead }: { lead: Lead }) {
  const { t } = useTranslation('leads')
  const locale = useLocale()
  const can = useCan()
  const canEdit = useCanEditOwned()
  const { data: me } = useMe()
  const editable = canEdit(lead.owner.id) && !lead.archived_at
  const may = {
    restore: can('records.restore'),
    create: can('records.create'),
    reassign: can('records.reassign'),
  }
  const path = { params: { path: { lead_id: lead.id } } }
  const version = { version: lead.version }
  const statusMessage = (l: Lead) => t('toasts.statusChanged', { status: t(`status.${l.status}`) })

  const markContacted = useLeadMutation(
    lead.id,
    () => call(api.POST('/api/v1/leads/{lead_id}/mark-contacted', { ...path, body: version })),
    statusMessage,
  )
  const qualify = useLeadMutation(
    lead.id,
    () => call(api.POST('/api/v1/leads/{lead_id}/qualify', { ...path, body: version })),
    statusMessage,
  )
  const reopen = useLeadMutation(
    lead.id,
    () => call(api.POST('/api/v1/leads/{lead_id}/reopen', { ...path, body: version })),
    statusMessage,
  )
  const assign = useLeadMutation(
    lead.id,
    (ownerId: string) =>
      call(
        api.POST('/api/v1/leads/{lead_id}/assign', {
          ...path,
          body: { owner_id: ownerId, version: lead.version },
        }),
      ),
    () => t('toasts.assigned'),
  )
  const archive = useLeadMutation(
    lead.id,
    async () => {
      await call(api.DELETE('/api/v1/leads/{lead_id}', path))
      return call(api.GET('/api/v1/leads/{lead_id}', path))
    },
    () => t('toasts.archived'),
  )
  const restore = useLeadMutation(
    lead.id,
    () => call(api.POST('/api/v1/leads/{lead_id}/restore', path)),
    () => t('toasts.restored'),
  )
  const unknownBant = BANT_ITEMS.filter((item) => lead.qualification[item].status === 'unknown')
  const readOnly = lead.status === 'converted' || lead.status === 'disqualified'

  return (
    <div className="flex flex-col gap-3">
      {readOnly ? (
        <Alert>
          <AlertDescription>
            {lead.disqualification
              ? t('disqualify.info', {
                  date: lead.disqualification.disqualified_at
                    ? formatDate(lead.disqualification.disqualified_at, locale)
                    : '',
                  reason: lead.disqualification.reason
                    ? referenceName(lead.disqualification.reason, locale)
                    : '',
                })
              : t('detail.readOnly', { status: t(`status.${lead.status}`) })}
            {lead.disqualification?.note ? ` — ${lead.disqualification.note}` : ''}
          </AlertDescription>
        </Alert>
      ) : null}
      {lead.status === 'qualified' ? (
        <p className="text-sm text-muted-foreground">{t('detail.conversionLater')}</p>
      ) : null}
      <div className="flex flex-wrap gap-2" role="group" aria-label={t('actions.title')}>
        {editable && lead.status === 'new' ? (
          <Button
            type="button"
            disabled={markContacted.isPending}
            onClick={() => {
              markContacted.mutate(undefined)
            }}
          >
            {t('actions.markContacted')}
          </Button>
        ) : null}
        {editable && lead.status === 'contacted' ? (
          <Button
            type="button"
            disabled={qualify.isPending || unknownBant.length > 0}
            title={unknownBant.length > 0 ? t('bant.incomplete') : undefined}
            onClick={() => {
              qualify.mutate(undefined)
            }}
          >
            {t('actions.qualify')}
          </Button>
        ) : null}
        {editable && !readOnly ? <DisqualifyDialog lead={lead} /> : null}
        {lead.status === 'disqualified' && may.restore && !lead.archived_at ? (
          <Button
            type="button"
            variant="outline"
            disabled={reopen.isPending}
            onClick={() => {
              reopen.mutate(undefined)
            }}
          >
            {t('actions.reopen')}
          </Button>
        ) : null}
        {editable && !readOnly ? (
          <Link to={`/leads/${lead.id}/edit`} className={buttonVariants({ variant: 'outline' })}>
            {t('actions.edit')}
          </Link>
        ) : null}
        {!readOnly &&
        !lead.archived_at &&
        may.create &&
        !may.reassign &&
        me &&
        lead.owner.id !== me.id ? (
          <Button
            type="button"
            variant="outline"
            disabled={assign.isPending}
            onClick={() => {
              assign.mutate(me.id)
            }}
          >
            {t('actions.takeOver')}
          </Button>
        ) : null}
        {!readOnly && !lead.archived_at && may.reassign ? (
          <AssignControl
            current={lead.owner.id}
            pending={assign.isPending}
            label={t('actions.assignTo')}
            buttonLabel={t('actions.assign')}
            onAssign={(id) => {
              assign.mutate(id)
            }}
          />
        ) : null}
        {editable ? (
          <ConfirmButton
            label={t('actions.archive')}
            title={t('actions.archive')}
            description={t('actions.confirmArchive', { title: lead.title })}
            variant="destructive"
            onConfirm={() => {
              archive.mutate(undefined)
            }}
          />
        ) : null}
        {lead.archived_at && may.restore ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              restore.mutate(undefined)
            }}
          >
            {t('actions.restore')}
          </Button>
        ) : null}
      </div>
    </div>
  )
}

function DisqualifyDialog({ lead }: { lead: Lead }) {
  const { t } = useTranslation('leads')
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const reasons = useReferenceList('disqualification-reasons')
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [missing, setMissing] = useState(false)
  const disqualify = useLeadMutation(
    lead.id,
    () =>
      call(
        api.POST('/api/v1/leads/{lead_id}/disqualify', {
          params: { path: { lead_id: lead.id } },
          body: { reason_id: reason, note: note.trim() || null, version: lead.version },
        }),
      ),
    (l) => t('toasts.statusChanged', { status: t(`status.${l.status}`) }),
  )
  if (!open) {
    return (
      <Button
        type="button"
        variant="destructive"
        onClick={() => {
          setOpen(true)
        }}
      >
        {t('actions.disqualify')}
      </Button>
    )
  }
  return (
    <form
      aria-label={t('disqualify.title')}
      className="flex w-full flex-col gap-3 rounded-lg border p-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (!reason) {
          setMissing(true)
          return
        }
        disqualify.mutate(undefined, {
          onSuccess: () => {
            setOpen(false)
          },
        })
      }}
    >
      <FormField label={t('disqualify.reason')} error={missing ? 'validation.required' : undefined}>
        {(control) => (
          <NativeSelect
            {...control}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value)
              setMissing(false)
            }}
          >
            <option value="">{t('disqualify.chooseReason')}</option>
            {(reasons.data ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {referenceName(item, locale)}
              </option>
            ))}
          </NativeSelect>
        )}
      </FormField>
      <FormField label={t('disqualify.note')}>
        {(control) => (
          <Textarea
            {...control}
            rows={2}
            value={note}
            onChange={(e) => {
              setNote(e.target.value)
            }}
          />
        )}
      </FormField>
      <div className="flex gap-2">
        <Button type="submit" variant="destructive" disabled={disqualify.isPending}>
          {t('disqualify.confirm')}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setOpen(false)
          }}
        >
          {tc('actions.cancel')}
        </Button>
      </div>
    </form>
  )
}

/** FR-LEAD-03: BANT statuses with notes, fit flag and the live score. */
function BantCard({ lead }: { lead: Lead }) {
  const { t } = useTranslation('leads')
  const canEdit = useCanEditOwned()
  const editable =
    canEdit(lead.owner.id) &&
    !lead.archived_at &&
    lead.status !== 'converted' &&
    lead.status !== 'disqualified'
  const [draft, setDraft] = useState(() => ({
    items: Object.fromEntries(
      BANT_ITEMS.map((item) => [item, { ...lead.qualification[item] }]),
    ) as Record<BantItem, { status: BantStatus; note: string }>,
    fits: lead.qualification.fits_target_profile,
  }))
  // Same rule as the server: yes 25, partial 12.5, no/unknown 0, rounded half up.
  const score = Math.round(
    BANT_ITEMS.reduce((sum, item) => sum + POINTS[draft.items[item].status], 0),
  )
  const save = useLeadMutation(
    lead.id,
    () =>
      call(
        api.PATCH('/api/v1/leads/{lead_id}', {
          params: { path: { lead_id: lead.id } },
          body: {
            version: lead.version,
            qualification: { ...draft.items, fits_target_profile: draft.fits },
          },
        }),
      ),
    () => t('toasts.saved'),
  )
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>{t('bant.title')}</CardTitle>
        <span className="text-sm" data-testid="bant-score">
          {t('bant.score')}: <strong>{score}</strong>
        </span>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate(undefined)
          }}
        >
          <fieldset disabled={!editable} className="flex flex-col gap-4">
            {BANT_ITEMS.map((item) => (
              <div key={item} className="grid gap-2 sm:grid-cols-[8rem_10rem_1fr] sm:items-center">
                <span className="text-sm font-medium" id={`bant-${item}`}>
                  {t(`bant.${item}`)}
                </span>
                <NativeSelect
                  aria-labelledby={`bant-${item}`}
                  value={draft.items[item].status}
                  onChange={(e) => {
                    const status = e.target.value as BantStatus
                    setDraft((d) => ({
                      ...d,
                      items: { ...d.items, [item]: { ...d.items[item], status } },
                    }))
                  }}
                >
                  {BANT_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {t(`bant.status.${status}`)}
                    </option>
                  ))}
                </NativeSelect>
                <Input
                  aria-label={`${t(`bant.${item}`)}: ${t('bant.note')}`}
                  value={draft.items[item].note}
                  maxLength={2000}
                  onChange={(e) => {
                    const note = e.target.value
                    setDraft((d) => ({
                      ...d,
                      items: { ...d.items, [item]: { ...d.items[item], note } },
                    }))
                  }}
                />
              </div>
            ))}
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.fits}
                onChange={(e) => {
                  setDraft((d) => ({ ...d, fits: e.target.checked }))
                }}
              />
              {t('bant.fits')}
            </label>
            {editable ? (
              <Button type="submit" className="self-start" disabled={save.isPending}>
                {t('bant.save')}
              </Button>
            ) : null}
          </fieldset>
        </form>
      </CardContent>
    </Card>
  )
}
