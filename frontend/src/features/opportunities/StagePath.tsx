import { useTranslation } from 'react-i18next'

import { useLocale } from '@/lib/useLocale'
import { cn } from '@/lib/utils'

import { stageName, type Opportunity } from './opportunityValues'

const TICK = '✓'

/** Current: brand fill; passed: peach; upcoming: muted (each pair 4.5:1 or more). */
function toneOf(isCurrent: boolean, isPassed: boolean): string {
  if (isCurrent) return 'bg-primary text-primary-foreground shadow-xs'
  if (isPassed) return 'bg-accent text-accent-foreground'
  return 'bg-muted text-muted-foreground'
}

interface PathStage {
  id: string
  name_en: string
  name_bg: string
  position: number
}

/**
 * Loop 3: the sales path, as in leading CRMs. The open stages run left to right, followed
 * by the outcome. Passed stages are ticked, the current one is filled with the brand, and
 * on an open opportunity the owner can click any other open stage to move there (FR-OPP-02,
 * the same `move` call as the "Stage" list). The list stays as the keyboard-and-form way.
 */
export function StagePath({
  opportunity: o,
  stages,
  onMove,
  pending,
}: {
  opportunity: Opportunity
  /** Active open stages of the pipeline. */
  stages: PathStage[]
  /** Given when the user may move the opportunity; omitted for read-only. */
  onMove?: ((stageId: string) => void) | undefined
  pending: boolean
}) {
  const { t } = useTranslation('opportunities')
  const locale = useLocale()
  const ordered = [...stages].sort((a, b) => a.position - b.position)
  const type = o.stage.stage_type
  const currentIndex = type === 'open' ? ordered.findIndex((s) => s.id === o.stage.id) : -1
  // Closed: every open stage counts as passed.
  const passedUpTo = type === 'open' ? currentIndex : ordered.length
  const segment =
    'flex min-h-9 min-w-max flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors duration-150 pointer-coarse:min-h-11'

  return (
    <ol aria-label={t('path.label')} className="flex gap-1 overflow-x-auto pb-1">
      {ordered.map((stage, index) => {
        const name = stageName(stage, locale)
        const isCurrent = index === currentIndex
        const isPassed = index < passedUpTo
        const tone = toneOf(isCurrent, isPassed)
        const content = (
          <>
            {isPassed ? <span aria-hidden="true">{TICK}</span> : null}
            {name}
            {isPassed ? <span className="sr-only">{t('path.passed')}</span> : null}
          </>
        )
        return (
          <li
            key={stage.id}
            className="flex min-w-max flex-1"
            aria-current={isCurrent ? 'step' : undefined}
          >
            {onMove && type === 'open' && !isCurrent ? (
              <button
                type="button"
                className={cn(
                  segment,
                  tone,
                  'cursor-pointer hover:bg-primary/15 hover:text-accent-foreground disabled:cursor-wait',
                )}
                disabled={pending}
                aria-label={t('path.moveTo', { stage: name })}
                onClick={() => {
                  onMove(stage.id)
                }}
              >
                {content}
              </button>
            ) : (
              <span className={cn(segment, tone)}>{content}</span>
            )}
          </li>
        )
      })}
      <li className="flex min-w-max flex-1" aria-current={type !== 'open' ? 'step' : undefined}>
        <span
          data-testid="path-outcome"
          className={cn(
            segment,
            type === 'won' && 'bg-success/10 text-success',
            type === 'lost' && 'bg-destructive/10 text-destructive',
            type === 'open' && 'border border-dashed text-muted-foreground',
          )}
        >
          {type === 'open' ? t('path.closed') : stageName(o.stage, locale)}
        </span>
      </li>
    </ol>
  )
}
