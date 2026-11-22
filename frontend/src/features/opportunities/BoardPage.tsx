import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
} from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { api, call } from '@/api/client'
import { ErrorState } from '@/components/ErrorState'
import { Loading } from '@/components/Loading'
import { NativeSelect } from '@/components/NativeSelect'
import { PageHeader } from '@/components/PageHeader'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { buttonVariants } from '@/components/ui/button'
import { useNotify } from '@/lib/notify'
import { formatDay, formatMoney, formatNumber } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useListParams } from '@/lib/useListParams'
import { useLocale } from '@/lib/useLocale'
import { cn } from '@/lib/utils'

import { CloseForm } from './CloseForm'
import { stageName, type BoardCard, type BoardData, type StageSummary } from './opportunityValues'
import { StaleBadge } from './StageBadge'

const GRIP = '⠿'

/** Where a card can go: another open stage, or closed as won or lost. */
type Target = { kind: 'stage'; stageId: string } | { kind: 'won' } | { kind: 'lost' }

function parseTarget(id: string): Target | null {
  if (id === 'close:won') return { kind: 'won' }
  if (id === 'close:lost') return { kind: 'lost' }
  if (id.startsWith('stage:')) return { kind: 'stage', stageId: id.slice('stage:'.length) }
  return null
}

/** FR-OPP-03: Kanban of open stages with totals; drag (or choose) to move or close. */
export function BoardPage() {
  const { t } = useTranslation('opportunities')
  const locale = useLocale()
  const can = useCan()
  const notify = useNotify()
  const queryClient = useQueryClient()
  const list = useListParams({ sort: '', filters: ['owner_id'] as const })
  const [losing, setLosing] = useState<BoardCard | null>(null)
  const board = useQuery({
    queryKey: ['opportunities', 'board', list.key],
    placeholderData: keepPreviousData,
    queryFn: () =>
      call(
        api.GET('/api/v1/opportunities/board', {
          params: {
            query: list.filters.owner_id.length ? { owner_id: list.filters.owner_id } : {},
          },
        }),
      ),
  })
  const change = useMutation({
    mutationFn: ({ card, target }: { card: BoardCard; target: Target }) => {
      const path = { params: { path: { opp_id: card.id } } }
      return target.kind === 'stage'
        ? call(
            api.POST('/api/v1/opportunities/{opp_id}/move', {
              ...path,
              body: { stage_id: target.stageId, version: card.version },
            }),
          )
        : call(
            api.POST('/api/v1/opportunities/{opp_id}/close', {
              ...path,
              body: { outcome: 'won', version: card.version },
            }),
          )
    },
    onSuccess: async (updated) => {
      await queryClient.invalidateQueries({ queryKey: ['opportunities'] })
      await queryClient.invalidateQueries({ queryKey: ['organizations'] })
      notify.success(
        updated.stage.stage_type === 'won'
          ? t('toasts.won')
          : t('toasts.stageChanged', { stage: stageName(updated.stage, locale) }),
      )
    },
    onError: async (error) => {
      await queryClient.invalidateQueries({ queryKey: ['opportunities', 'board'] })
      notify.error(error)
    },
  })
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  )

  const cards = new Map(
    (board.data?.columns ?? []).flatMap((column) =>
      column.cards.map((card) => [card.id, { card, stage: column.stage }] as const),
    ),
  )
  const apply = (card: BoardCard, from: StageSummary, target: Target) => {
    if (target.kind === 'lost') {
      setLosing(card)
      return
    }
    if (target.kind === 'stage' && target.stageId === from.id) return
    change.mutate({ card, target })
  }
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    const found = cards.get(String(active.id))
    const target = over ? parseTarget(String(over.id)) : null
    if (found && target) apply(found.card, found.stage, target)
  }
  const targetName = (id: string | number | undefined) => {
    const target = id === undefined ? null : parseTarget(String(id))
    if (!target) return ''
    if (target.kind === 'won') return t('board.dropWon')
    if (target.kind === 'lost') return t('board.dropLost')
    const column = board.data?.columns.find((c) => c.stage.id === target.stageId)
    return column ? stageName(column.stage, locale) : ''
  }
  const cardName = (id: string | number) => cards.get(String(id))?.card.name ?? ''
  const announcements: Announcements = {
    onDragStart: ({ active }) => t('board.announce.start', { name: cardName(active.id) }),
    onDragOver: ({ active, over }) =>
      over
        ? t('board.announce.over', { name: cardName(active.id), target: targetName(over.id) })
        : t('board.announce.outside', { name: cardName(active.id) }),
    onDragEnd: ({ active, over }) =>
      over
        ? t('board.announce.dropped', { name: cardName(active.id), target: targetName(over.id) })
        : t('board.announce.cancelled', { name: cardName(active.id) }),
    onDragCancel: ({ active }) => t('board.announce.cancelled', { name: cardName(active.id) }),
  }

  return (
    <section className="mx-auto flex max-w-[100rem] flex-col gap-4">
      <PageHeader
        title={t('board.title')}
        actions={
          <div className="flex items-center gap-2">
            <NativeSelect
              aria-label={t('list.owner')}
              value={list.filters.owner_id[0] ?? ''}
              onChange={(e) => {
                list.update({ owner_id: e.target.value || null })
              }}
              className="w-40"
            >
              <option value="">{t('list.everyone')}</option>
              <option value="me">{t('list.mine')}</option>
            </NativeSelect>
            <Link to="/opportunities" className={buttonVariants({ variant: 'outline' })}>
              {t('board.listView')}
            </Link>
            {can('records.create') ? (
              <Link to="/opportunities/new" className={buttonVariants()}>
                {t('list.new')}
              </Link>
            ) : null}
          </div>
        }
      />
      <p className="text-sm text-muted-foreground">{t('board.help')}</p>
      {board.isError ? (
        <ErrorState
          error={board.error}
          onRetry={() => {
            void board.refetch()
          }}
        />
      ) : null}
      {board.data?.truncated ? (
        <Alert>
          <AlertDescription>{t('board.truncated')}</AlertDescription>
        </Alert>
      ) : null}
      {losing ? (
        <CloseForm
          opportunity={losing}
          outcome="lost"
          onDone={() => {
            setLosing(null)
          }}
        />
      ) : null}
      {board.data ? (
        <DndContext
          sensors={sensors}
          onDragEnd={onDragEnd}
          accessibility={{
            announcements,
            screenReaderInstructions: { draggable: t('board.announce.instructions') },
          }}
        >
          <BoardColumns data={board.data} onChoose={apply} />
          <div className="grid gap-3 sm:grid-cols-2">
            <DropArea id="close:won" label={t('board.dropWon')} tone="won" />
            <DropArea id="close:lost" label={t('board.dropLost')} tone="lost" />
          </div>
        </DndContext>
      ) : board.isPending ? (
        <Loading />
      ) : null}
    </section>
  )
}

function BoardColumns({
  data,
  onChoose,
}: {
  data: BoardData
  onChoose: (card: BoardCard, from: StageSummary, target: Target) => void
}) {
  const { t } = useTranslation('opportunities')
  const locale = useLocale()
  const stages = data.columns.map((column) => column.stage)
  return (
    <div className="grid gap-3 overflow-x-auto md:grid-flow-col md:auto-cols-[minmax(16rem,1fr)]">
      {data.columns.map((column) => (
        <Column key={column.stage.id} stageId={column.stage.id}>
          <header className="flex flex-col gap-1 border-b pb-2">
            <h2 className="font-medium">{stageName(column.stage, locale)}</h2>
            <p className="text-xs text-muted-foreground" data-testid={`totals-${column.stage.id}`}>
              {t('board.totals', {
                count: column.count,
                countText: formatNumber(column.count, locale),
                total: formatMoney(column.total_amount, locale),
                weighted: formatMoney(column.weighted_amount, locale),
              })}
            </p>
          </header>
          <ul className="flex flex-col gap-2" aria-label={stageName(column.stage, locale)}>
            {column.cards.map((card) => (
              <Card
                key={card.id}
                card={card}
                stage={column.stage}
                stages={stages}
                onChoose={onChoose}
              />
            ))}
          </ul>
        </Column>
      ))}
    </div>
  )
}

function Column({ stageId, children }: { stageId: string; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: `stage:${stageId}` })
  return (
    <div
      ref={setNodeRef}
      className={cn(
        // Loop 3: a brand edge on each column; the column a card is over turns peach.
        'flex min-h-48 flex-col gap-2 rounded-lg border border-t-[3px] border-t-primary/70 bg-muted/40 p-3 transition-colors duration-150',
        isOver && 'bg-accent/70 ring-2 ring-primary',
      )}
    >
      {children}
    </div>
  )
}

function DropArea({ id, label, tone }: { id: string; label: string; tone: 'won' | 'lost' }) {
  const { setNodeRef, isOver } = useDroppable({ id })
  return (
    <div
      ref={setNodeRef}
      data-testid={id}
      className={cn(
        'rounded-lg border-2 border-dashed p-4 text-center text-sm',
        'transition-colors duration-150',
        tone === 'won'
          ? 'border-success/60 text-success'
          : 'border-destructive/60 text-destructive',
        isOver && (tone === 'won' ? 'bg-success/10' : 'bg-destructive/10'),
      )}
    >
      {label}
    </div>
  )
}

function Card({
  card,
  stage,
  stages,
  onChoose,
}: {
  card: BoardCard
  stage: StageSummary
  stages: StageSummary[]
  onChoose: (card: BoardCard, from: StageSummary, target: Target) => void
}) {
  const { t } = useTranslation('opportunities')
  const locale = useLocale()
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: card.id,
    disabled: !card.can_edit,
  })
  const style = { transform: CSS.Translate.toString(transform) }
  return (
    <li
      ref={setNodeRef}
      style={style}
      className={cn(
        // Loop 3: cards lift on hover and tilt slightly while dragged.
        'flex flex-col gap-1 rounded-md border bg-card p-3 text-sm shadow-xs transition-[box-shadow,border-color] duration-150 hover:border-primary/40 hover:shadow-md',
        card.can_edit && 'cursor-grab active:cursor-grabbing',
        isDragging && 'z-10 rotate-1 opacity-90 shadow-lg ring-1 ring-primary/40',
      )}
      data-testid={`card-${card.id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <Link to={`/opportunities/${card.id}`} className="font-medium hover:underline">
          {card.name}
        </Link>
        {card.can_edit ? (
          <button
            type="button"
            className="rounded px-1 text-muted-foreground hover:bg-muted"
            aria-label={t('board.dragHandle', { name: card.name })}
            {...attributes}
            {...listeners}
          >
            {GRIP}
          </button>
        ) : null}
      </div>
      <span className="text-muted-foreground">{card.organization.name}</span>
      <span className="flex flex-wrap items-center gap-2">
        {card.amount ? <span>{formatMoney(card.amount, locale)}</span> : null}
        {card.expected_close_date ? (
          <span className="text-xs text-muted-foreground">
            {formatDay(card.expected_close_date, locale)}
          </span>
        ) : null}
        {card.is_stale ? <StaleBadge /> : null}
      </span>
      <span className="text-xs text-muted-foreground">{card.owner.full_name}</span>
      {card.can_edit ? (
        <NativeSelect
          aria-label={t('board.moveCard', { name: card.name })}
          value=""
          className="mt-1 h-8 text-xs"
          onChange={(e) => {
            const target = parseTarget(e.target.value)
            if (target) onChoose(card, stage, target)
          }}
        >
          <option value="">{t('board.moveTo')}</option>
          {stages
            .filter((s) => s.id !== stage.id)
            .map((s) => (
              <option key={s.id} value={`stage:${s.id}`}>
                {stageName(s, locale)}
              </option>
            ))}
          <option value="close:won">{t('board.dropWon')}</option>
          <option value="close:lost">{t('board.dropLost')}</option>
        </NativeSelect>
      ) : null}
    </li>
  )
}
