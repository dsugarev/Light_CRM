import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'

import { api, call } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { RecordTimeline } from '@/features/activities/RecordTimeline'
import { AssignControl } from '@/features/auth/AssignControl'
import { useMe } from '@/features/auth/useMe'
import { useCanEditOwned } from '@/features/auth/useOwnership'
import { referenceName } from '@/features/reference/useReferenceList'
import { formatDate, formatDateTime, formatDay, formatMoney } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useLocale } from '@/lib/useLocale'

import { CloseForm } from './CloseForm'
import { stageName, type Opportunity } from './opportunityValues'
import { StageBadge, StaleBadge } from './StageBadge'
import { useOpportunityMutation } from './useOpportunityMutation'
import { usePipeline } from './usePipeline'

export function OpportunityPage() {
  const { opportunityId = '' } = useParams()
  const { t } = useTranslation('opportunities')
  const locale = useLocale()
  const opportunity = useQuery({
    queryKey: ['opportunities', opportunityId],
    queryFn: () =>
      call(
        api.GET('/api/v1/opportunities/{opp_id}', {
          params: { path: { opp_id: opportunityId } },
        }),
      ),
  })
  if (opportunity.isError) return <ErrorState error={opportunity.error} />
  if (!opportunity.data) return <Loading />
  const o = opportunity.data
  const probability = o.probability_overridden
    ? t('detail.probabilityOverridden', { value: o.probability })
    : `${String(o.probability)}%`
  const rows: [string, React.ReactNode][] = [
    [
      t('fields.organization'),
      <Link key="org" className="hover:underline" to={`/organizations/${o.organization.id}`}>
        {o.organization.name}
      </Link>,
    ],
    [
      t('fields.contact'),
      o.primary_contact ? (
        <Link className="hover:underline" to={`/contacts/${o.primary_contact.id}`}>
          {o.primary_contact.name}
        </Link>
      ) : null,
    ],
    [t('fields.amount'), o.amount ? formatMoney(o.amount, locale) : null],
    [t('fields.probability'), probability],
    [t('fields.weighted'), o.weighted_amount ? formatMoney(o.weighted_amount, locale) : null],
    [
      t('fields.expectedCloseDate'),
      o.expected_close_date ? formatDay(o.expected_close_date, locale) : null,
    ],
    [
      t('fields.actualCloseDate'),
      o.actual_close_date ? formatDay(o.actual_close_date, locale) : null,
    ],
    [t('fields.lossReason'), o.loss_reason ? referenceName(o.loss_reason, locale) : null],
    [t('fields.competitor'), o.competitor],
    [t('fields.nextStep'), o.next_step],
    [t('fields.owner'), o.owner.full_name],
    [
      t('fields.sourceLead'),
      o.source_lead ? (
        <Link className="hover:underline" to={`/leads/${o.source_lead.id}`}>
          {o.source_lead.name}
        </Link>
      ) : null,
    ],
  ]
  return (
    <section className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title={o.name}
        actions={
          <span className="flex items-center gap-2">
            {o.is_stale ? <StaleBadge /> : null}
            <StageBadge stage={o.stage} />
          </span>
        }
      />
      <OpportunityActions key={`${o.id}-${String(o.version)}`} opportunity={o} />
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
            {o.description ? (
              <p className="mt-4 whitespace-pre-wrap text-sm">{o.description}</p>
            ) : null}
            <p className="mt-4 text-xs text-muted-foreground">
              {t('detail.createdBy', {
                name: o.created_by?.full_name ?? '',
                date: formatDate(o.created_at, locale),
              })}
            </p>
          </CardContent>
        </Card>
        <StageHistory opportunityId={o.id} version={o.version} />
      </div>
      <RecordTimeline record={{ kind: 'opportunity', id: o.id }} canLog={!o.archived_at} />
    </section>
  )
}

type Panel = 'none' | 'won' | 'lost'

function OpportunityActions({ opportunity: o }: { opportunity: Opportunity }) {
  const { t } = useTranslation('opportunities')
  const locale = useLocale()
  const can = useCan()
  const canEdit = useCanEditOwned()
  const { data: me } = useMe()
  const pipeline = usePipeline()
  const [panel, setPanel] = useState<Panel>('none')
  const isOpen = o.stage.stage_type === 'open'
  const editable = canEdit(o.owner.id) && !o.archived_at
  const may = {
    restore: can('records.restore'),
    create: can('records.create'),
    reassign: can('records.reassign'),
  }
  const openStages = (pipeline.data?.stages ?? []).filter(
    (s) => s.is_active && s.stage_type === 'open',
  )
  const [target, setTarget] = useState(isOpen ? o.stage.id : (openStages[0]?.id ?? ''))
  const path = { params: { path: { opp_id: o.id } } }
  const stageMessage = (updated: Opportunity) =>
    t('toasts.stageChanged', { stage: stageName(updated.stage, locale) })

  const move = useOpportunityMutation(
    o.id,
    (stageId: string) =>
      call(
        api.POST('/api/v1/opportunities/{opp_id}/move', {
          ...path,
          body: { stage_id: stageId, version: o.version },
        }),
      ),
    stageMessage,
  )
  const reopen = useOpportunityMutation(
    o.id,
    (stageId: string) =>
      call(
        api.POST('/api/v1/opportunities/{opp_id}/reopen', {
          ...path,
          body: { stage_id: stageId, version: o.version },
        }),
      ),
    () => t('toasts.reopened'),
  )
  const assign = useOpportunityMutation(
    o.id,
    (ownerId: string) =>
      call(
        api.POST('/api/v1/opportunities/{opp_id}/assign', {
          ...path,
          body: { owner_id: ownerId, version: o.version },
        }),
      ),
    () => t('toasts.assigned'),
  )
  const archive = useOpportunityMutation(
    o.id,
    async () => {
      await call(api.DELETE('/api/v1/opportunities/{opp_id}', path))
      return call(api.GET('/api/v1/opportunities/{opp_id}', path))
    },
    () => t('toasts.archived'),
  )
  const restore = useOpportunityMutation(
    o.id,
    () => call(api.POST('/api/v1/opportunities/{opp_id}/restore', path)),
    () => t('toasts.restored'),
  )
  const reopenStage = target !== '' ? target : (openStages[0]?.id ?? '')

  return (
    <div className="flex flex-col gap-3">
      {!isOpen ? (
        <Alert>
          <AlertDescription>
            {o.stage.stage_type === 'won'
              ? t('detail.wonInfo', {
                  date: o.actual_close_date ? formatDay(o.actual_close_date, locale) : '',
                })
              : t('detail.lostInfo', {
                  date: o.actual_close_date ? formatDay(o.actual_close_date, locale) : '',
                  reason: o.loss_reason ? referenceName(o.loss_reason, locale) : '',
                })}
          </AlertDescription>
        </Alert>
      ) : null}
      <div
        className="flex flex-wrap items-center gap-2"
        role="group"
        aria-label={t('actions.title')}
      >
        {editable && isOpen && openStages.length > 0 ? (
          <div className="flex items-center gap-2">
            <NativeSelect
              aria-label={t('actions.moveTo')}
              value={target}
              onChange={(e) => {
                setTarget(e.target.value)
              }}
              className="w-56"
            >
              {openStages.map((stage) => (
                <option key={stage.id} value={stage.id}>
                  {stageName(stage, locale)}
                </option>
              ))}
            </NativeSelect>
            <Button
              type="button"
              variant="outline"
              disabled={move.isPending || target === o.stage.id}
              onClick={() => {
                move.mutate(target)
              }}
            >
              {t('actions.move')}
            </Button>
          </div>
        ) : null}
        {editable && isOpen ? (
          <Button
            type="button"
            onClick={() => {
              setPanel('won')
            }}
          >
            {t('actions.closeWon')}
          </Button>
        ) : null}
        {editable && isOpen ? (
          <Button
            type="button"
            variant="destructive"
            onClick={() => {
              setPanel('lost')
            }}
          >
            {t('actions.closeLost')}
          </Button>
        ) : null}
        {!isOpen && may.restore && !o.archived_at && openStages.length > 0 ? (
          <div className="flex items-center gap-2">
            <NativeSelect
              aria-label={t('actions.reopenInto')}
              value={reopenStage}
              onChange={(e) => {
                setTarget(e.target.value)
              }}
              className="w-56"
            >
              {openStages.map((stage) => (
                <option key={stage.id} value={stage.id}>
                  {stageName(stage, locale)}
                </option>
              ))}
            </NativeSelect>
            <Button
              type="button"
              variant="outline"
              disabled={reopen.isPending || !reopenStage}
              onClick={() => {
                reopen.mutate(reopenStage)
              }}
            >
              {t('actions.reopen')}
            </Button>
          </div>
        ) : null}
        {editable && isOpen ? (
          <Link
            to={`/opportunities/${o.id}/edit`}
            className={buttonVariants({ variant: 'outline' })}
          >
            {t('actions.edit')}
          </Link>
        ) : null}
        {isOpen && !o.archived_at && may.create && !may.reassign && me && o.owner.id !== me.id ? (
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
        {isOpen && !o.archived_at && may.reassign ? (
          <AssignControl
            current={o.owner.id}
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
            description={t('actions.confirmArchive', { name: o.name })}
            variant="destructive"
            onConfirm={() => {
              archive.mutate(undefined)
            }}
          />
        ) : null}
        {o.archived_at && may.restore ? (
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
      {panel !== 'none' ? (
        <CloseForm
          opportunity={o}
          outcome={panel}
          onDone={() => {
            setPanel('none')
          }}
        />
      ) : null}
    </div>
  )
}

/** FR-OPP-02 AC2: who changed the stage, when, from and to. */
function StageHistory({ opportunityId, version }: { opportunityId: string; version: number }) {
  const { t } = useTranslation('opportunities')
  const locale = useLocale()
  const history = useQuery({
    queryKey: ['opportunities', opportunityId, 'stage-history', version],
    queryFn: () =>
      call(
        api.GET('/api/v1/opportunities/{opp_id}/stage-history', {
          params: { path: { opp_id: opportunityId } },
        }),
      ),
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('history.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        {history.data ? (
          <ol className="flex flex-col gap-2 text-sm">
            {history.data.map((change) => (
              <li key={change.id} className="flex flex-col">
                <span>
                  {change.from_stage
                    ? t('history.moved', {
                        from: stageName(change.from_stage, locale),
                        to: stageName(change.to_stage, locale),
                      })
                    : t('history.created', { to: stageName(change.to_stage, locale) })}
                </span>
                <span className="text-xs text-muted-foreground">
                  {`${change.changed_by?.full_name ?? ''} · ${formatDateTime(change.changed_at, locale)}`}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <Loading />
        )}
      </CardContent>
    </Card>
  )
}
