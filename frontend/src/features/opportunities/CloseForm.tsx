import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, call } from '@/api/client'
import { FormField } from '@/components/FormField'
import { NativeSelect } from '@/components/NativeSelect'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { referenceName, useReferenceList } from '@/features/reference/useReferenceList'
import { useLocale } from '@/lib/useLocale'

import { useOpportunityMutation } from './useOpportunityMutation'

interface CloseFormProps {
  opportunity: { id: string; name: string; version: number; competitor?: string | null }
  outcome: 'won' | 'lost'
  onDone: () => void
}

/** FR-OPP-05: close as won or lost; lost needs a loss reason, the date defaults to today. */
export function CloseForm({ opportunity, outcome, onDone }: CloseFormProps) {
  const { t } = useTranslation('opportunities')
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const reasons = useReferenceList('loss-reasons')
  const [reason, setReason] = useState('')
  const [competitor, setCompetitor] = useState(opportunity.competitor ?? '')
  const [date, setDate] = useState('')
  const [missing, setMissing] = useState(false)
  const close = useOpportunityMutation(
    opportunity.id,
    () =>
      call(
        api.POST('/api/v1/opportunities/{opp_id}/close', {
          params: { path: { opp_id: opportunity.id } },
          body: {
            outcome,
            version: opportunity.version,
            loss_reason_id: outcome === 'lost' ? reason : null,
            competitor: competitor.trim() || null,
            actual_close_date: date || null,
          },
        }),
      ),
    () => (outcome === 'won' ? t('toasts.won') : t('toasts.lost')),
  )
  const title = outcome === 'won' ? t('close.wonTitle') : t('close.lostTitle')
  return (
    <form
      aria-label={title}
      className="flex w-full flex-col gap-3 rounded-lg border p-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (outcome === 'lost' && !reason) {
          setMissing(true)
          return
        }
        close.mutate(undefined, { onSuccess: onDone })
      }}
    >
      <p className="text-sm font-medium">{`${title}: ${opportunity.name}`}</p>
      {outcome === 'lost' ? (
        <FormField
          label={t('close.reason')}
          required
          error={missing ? 'opportunity.loss_reason_required' : undefined}
        >
          {(control) => (
            <NativeSelect
              {...control}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value)
                setMissing(false)
              }}
            >
              <option value="">{t('close.chooseReason')}</option>
              {(reasons.data ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {referenceName(item, locale)}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
      ) : null}
      {outcome === 'lost' ? (
        <FormField label={t('fields.competitor')}>
          {(control) => (
            <Input
              {...control}
              value={competitor}
              maxLength={200}
              onChange={(e) => {
                setCompetitor(e.target.value)
              }}
            />
          )}
        </FormField>
      ) : null}
      <FormField label={t('close.date')} hint={t('close.dateHint')}>
        {(control) => (
          <Input
            {...control}
            type="date"
            value={date}
            onChange={(e) => {
              setDate(e.target.value)
            }}
          />
        )}
      </FormField>
      <div className="flex gap-2">
        <Button
          type="submit"
          variant={outcome === 'won' ? 'default' : 'destructive'}
          disabled={close.isPending}
        >
          {outcome === 'won' ? t('close.confirmWon') : t('close.confirmLost')}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {tc('actions.cancel')}
        </Button>
      </div>
    </form>
  )
}
