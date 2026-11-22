import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { ApiError } from '@/api/client'
import { NativeSelect } from '@/components/NativeSelect'
import { Textarea } from '@/components/Textarea'
import { FormField } from '@/components/FormField'
import { Button } from '@/components/ui/button'
import { useErrorText } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { useNotify } from '@/lib/notify'

import { Markdown } from './Markdown'
import type { RecordRef } from './stream'
import { ActionCard } from './ActionCard'
import {
  recordPath,
  useAssistantMutations,
  type ProposedAction,
  type RecordContext,
} from './useAssistant'

export interface ShownMessage {
  id: string | null // null while the answer is still arriving
  role: 'user' | 'assistant'
  content: string
  status: 'streaming' | 'complete' | 'stopped' | 'failed'
  errorCode: string | null
  tools: { tool: string; status: 'running' | 'done' }[]
  refs: RecordRef[]
  actions: ProposedAction[]
}

const TOOL_KEYS = [
  'search_leads',
  'search_opportunities',
  'search_organizations',
  'get_record',
  'list_activities',
  'pipeline_summary',
  'forecast_summary',
  'my_tasks',
  'search_contacts',
  'win_loss_summary',
  'lead_conversion_summary',
  'list_users',
  'get_settings',
  'list_values',
] as const

function useToolLabel() {
  const { t } = useTranslation('assistant')
  return (tool: string) => {
    if (tool.startsWith('propose_')) return t('tools.propose')
    return (TOOL_KEYS as readonly string[]).includes(tool)
      ? t(`tools.${tool as (typeof TOOL_KEYS)[number]}`)
      : t('tools.other')
  }
}

export function AssistantMessage({
  message,
  context,
}: {
  message: ShownMessage
  context: RecordContext | null
}) {
  const { t } = useTranslation('assistant')
  const errorText = useErrorText()
  const toolLabel = useToolLabel()
  const can = useCan()
  const mayCreate = can('records.create')
  const [copied, setCopied] = useState(false)
  const [noting, setNoting] = useState(false)

  if (message.role === 'user') {
    return (
      <li className="ml-8 rounded-lg bg-secondary px-3 py-2 text-sm whitespace-pre-wrap">
        <span className="sr-only">{t('you')}: </span>
        {message.content}
      </li>
    )
  }
  const running = message.tools.filter((call) => call.status === 'running')
  const finished = message.status !== 'streaming'
  const canSave = finished && message.id !== null && message.content !== ''
  const targets = noteTargets(context, message.refs)
  return (
    <li className="mr-4 space-y-2 text-sm">
      <span className="sr-only">{t('assistant')}: </span>
      {running.length > 0 ? (
        <p className="text-xs text-muted-foreground" role="status">
          {toolLabel(running[running.length - 1]?.tool ?? '')}
        </p>
      ) : null}
      {message.status === 'streaming' && message.content === '' && running.length === 0 ? (
        <p className="text-xs text-muted-foreground" role="status">
          {t('thinking')}
        </p>
      ) : null}
      {message.content ? <Markdown text={message.content} /> : null}
      {message.actions.length > 0 ? (
        <ul className="space-y-2" aria-label={t('action.list')}>
          {message.actions.map((action) => (
            <li key={action.id}>
              <ActionCard action={action} />
            </li>
          ))}
        </ul>
      ) : null}
      {message.status === 'stopped' ? (
        <p className="text-xs text-muted-foreground">{t('stopped')}</p>
      ) : null}
      {message.errorCode ? (
        <p role="alert" className="text-sm text-destructive">
          {errorText(message.errorCode)}
        </p>
      ) : null}
      {message.refs.length > 0 ? (
        <div>
          <p className="text-xs text-muted-foreground">{t('recordsMentioned')}</p>
          <ul className="flex flex-wrap gap-2">
            {message.refs.map((ref) => {
              const path = recordPath(ref.entity_type, ref.entity_id)
              return path ? (
                <li key={`${ref.entity_type}:${ref.entity_id}`}>
                  <Link to={path} className="text-xs text-primary underline underline-offset-2">
                    {ref.label}
                  </Link>
                </li>
              ) : null
            })}
          </ul>
        </div>
      ) : null}
      {canSave ? (
        <div className="flex gap-2">
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={() => {
              void navigator.clipboard.writeText(message.content).then(() => {
                setCopied(true)
              })
            }}
          >
            {copied ? t('copied') : t('copy')}
          </Button>
          {mayCreate && targets.length > 0 && !noting ? (
            <Button
              type="button"
              size="xs"
              variant="outline"
              onClick={() => {
                setNoting(true)
              }}
            >
              {t('saveAsNote')}
            </Button>
          ) : null}
        </div>
      ) : null}
      {noting && message.id ? (
        <NoteForm
          messageId={message.id}
          content={message.content}
          targets={targets}
          onDone={() => {
            setNoting(false)
          }}
        />
      ) : null}
    </li>
  )
}

interface Target {
  entity_type: 'lead' | 'opportunity' | 'organization' | 'contact'
  entity_id: string
  label: string | null // null: the record in view, named by its type
}

function noteTargets(context: RecordContext | null, refs: RecordRef[]): Target[] {
  const targets: Target[] = context ? [{ ...context, label: null }] : []
  for (const ref of refs) {
    if (!['lead', 'opportunity', 'organization', 'contact'].includes(ref.entity_type)) continue
    if (targets.some((t) => t.entity_id === ref.entity_id)) continue
    targets.push({
      entity_type: ref.entity_type as Target['entity_type'],
      entity_id: ref.entity_id,
      label: ref.label,
    })
  }
  return targets
}

/** FR-AI-04: the draft becomes a note only on this explicit, editable save. */
function NoteForm({
  messageId,
  content,
  targets,
  onDone,
}: {
  messageId: string
  content: string
  targets: Target[]
  onDone: () => void
}) {
  const notify = useNotify()
  const { t } = useTranslation('assistant')
  const { t: tc } = useTranslation()
  const errorText = useErrorText()
  const { saveAsNote } = useAssistantMutations()
  const [target, setTarget] = useState(targets[0]?.entity_id ?? '')
  const [text, setText] = useState(content)
  const chosen = targets.find((option) => option.entity_id === target)
  const typeName = (type: Target['entity_type']) => t(`recordType.${type}`)
  // A refused save names the field's reason (e.g. lead.archived) when there is one.
  const failure =
    saveAsNote.error instanceof ApiError
      ? (saveAsNote.error.errors[0]?.code ?? saveAsNote.error.code)
      : saveAsNote.error
        ? 'unknown'
        : null
  return (
    <form
      aria-label={t('saveAsNote')}
      className="space-y-2 rounded-lg border p-2"
      onSubmit={(event) => {
        event.preventDefault()
        if (!chosen) return
        saveAsNote.mutate(
          {
            messageId,
            body: { entity_type: chosen.entity_type, entity_id: chosen.entity_id, content: text },
          },
          {
            onSuccess: () => {
              notify.success(t('noteSaved'))
              onDone()
            },
          },
        )
      }}
    >
      <FormField label={t('noteTarget')} required>
        {(control) => (
          <NativeSelect
            {...control}
            value={target}
            onChange={(event) => {
              setTarget(event.target.value)
            }}
          >
            {targets.map((option) => (
              <option key={option.entity_id} value={option.entity_id}>
                {option.label === null
                  ? t('contextRecord', { type: typeName(option.entity_type) })
                  : `${typeName(option.entity_type)}: ${option.label}`}
              </option>
            ))}
          </NativeSelect>
        )}
      </FormField>
      <FormField label={t('noteContent')} required>
        {(control) => (
          <Textarea
            {...control}
            value={text}
            maxLength={10000}
            rows={6}
            onChange={(event) => {
              setText(event.target.value)
            }}
          />
        )}
      </FormField>
      {failure ? (
        <p role="alert" className="text-sm text-destructive">
          {errorText(failure)}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button
          type="submit"
          size="sm"
          disabled={!chosen || text.trim() === '' || saveAsNote.isPending}
        >
          {t('saveNote')}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onDone}>
          {tc('actions.cancel')}
        </Button>
      </div>
    </form>
  )
}
