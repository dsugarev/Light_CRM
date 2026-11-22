import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import type { Schemas } from '@/api/client'
import { detailListClass } from '@/components/detailList'
import { Button } from '@/components/ui/button'
import { PasswordLinkPanel } from '@/features/admin/PasswordLinkPanel'
import { useErrorText } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'
import { cn } from '@/lib/utils'

import { useAssistantMutations, type ProposedAction } from './useAssistant'

type Status = ProposedAction['status']

/**
 * FR-AI-09 (ADR 0030): an action the assistant proposed. Nothing changes until the user
 * presses Confirm; then exactly what the card shows runs, with the user's permissions.
 * Destructive actions (archive, close as lost, deactivate…) are shown in red.
 */
export function ActionCard({ action }: { action: ProposedAction }) {
  const { t } = useTranslation('assistant')
  const locale = useLocale()
  const errorText = useErrorText()
  const { confirmAction, cancelAction } = useAssistantMutations()
  const [current, setCurrent] = useState<ProposedAction>(action)
  const [link, setLink] = useState<Schemas['OneTimeLink'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const expired = current.status === 'proposed' && new Date(current.expires_at) <= new Date()
  const status: Status = expired ? 'expired' : current.status
  const pending = confirmAction.isPending || cancelAction.isPending
  const titleId = `action-${current.id}`

  return (
    <section
      aria-labelledby={titleId}
      data-testid="action-card"
      data-status={status}
      className={cn(
        'space-y-2 rounded-lg border p-3',
        current.destructive && status === 'proposed'
          ? 'border-destructive/60 bg-destructive/5'
          : 'border-primary/30 bg-accent/40',
      )}
    >
      <h3 id={titleId} className="text-sm font-semibold">
        {current.title}
      </h3>
      {current.target ? (
        <p className="text-xs text-muted-foreground">
          {current.target.url ? (
            <Link to={current.target.url} className="text-primary underline underline-offset-2">
              {current.target.label}
            </Link>
          ) : (
            current.target.label
          )}
        </p>
      ) : null}
      <dl className={cn(detailListClass('compact'), 'text-xs')}>
        {current.details.map((detail) => (
          <div key={`${detail.label}:${detail.value}`} className="contents">
            <dt className="text-muted-foreground">{detail.label}</dt>
            <dd className="min-w-0 break-words">{detail.value}</dd>
          </div>
        ))}
      </dl>
      {status === 'proposed' ? (
        <>
          <p className="text-xs text-muted-foreground">
            {current.destructive ? t('action.destructiveHint') : t('action.hint')}
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              size="xs"
              variant={current.destructive ? 'destructive' : 'default'}
              disabled={pending}
              onClick={() => {
                setError(null)
                confirmAction.mutate(current.id, {
                  onSuccess: (done) => {
                    setCurrent(done.action)
                    setLink(done.set_password ?? null)
                  },
                  onError: (failure) => {
                    setError(errorText((failure as { code?: string }).code ?? ''))
                    setCurrent({ ...current, status: 'failed' })
                  },
                })
              }}
            >
              {t('action.confirm')}
            </Button>
            <Button
              type="button"
              size="xs"
              variant="outline"
              disabled={pending}
              onClick={() => {
                cancelAction.mutate(current.id, {
                  onSuccess: () => {
                    setCurrent({ ...current, status: 'cancelled' })
                  },
                })
              }}
            >
              {t('action.cancel')}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {t('action.expires', { time: formatDateTime(current.expires_at, locale) })}
          </p>
        </>
      ) : (
        <p role="status" className={cn('text-xs', status === 'failed' && 'text-destructive')}>
          {t(`action.status.${status}`)}
          {status === 'confirmed' && current.result?.url ? (
            <>
              {' '}
              <Link to={current.result.url} className="text-primary underline underline-offset-2">
                {t('action.open', { label: current.result.label })}
              </Link>
            </>
          ) : null}
        </p>
      )}
      {(error ?? (current.error_code ? errorText(current.error_code) : null)) ? (
        <p role="alert" className="text-xs text-destructive">
          {error ?? errorText(current.error_code ?? '')}
        </p>
      ) : null}
      {link ? <PasswordLinkPanel link={link} name={current.result?.label ?? ''} /> : null}
    </section>
  )
}
