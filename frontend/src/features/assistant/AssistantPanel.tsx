import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Textarea } from '@/components/Textarea'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatDateTime } from '@/lib/format'
import { useLocale } from '@/lib/useLocale'

import { AssistantMessage, type ShownMessage } from './AssistantMessage'
import { streamMessage, type StreamEvent } from './stream'
import {
  ASSISTANT_KEY,
  useAssistantMutations,
  useConversation,
  useConversations,
  useRecordInView,
  type ChatMessage,
  type RecordContext,
} from './useAssistant'

const MAX_CHARS = 4000

interface LiveTurn {
  question: string
  answer: ShownMessage
  // Stored messages before this question; the server already holds the question and
  // the unfinished answer, which are shown from the live turn until it ends.
  before: number
}

function stored(message: ChatMessage): ShownMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    status: message.status,
    errorCode: message.error_code,
    tools: [],
    refs: message.record_refs,
  }
}

function applyEvent(answer: ShownMessage, event: StreamEvent): ShownMessage {
  switch (event.event) {
    case 'message_start':
      return { ...answer, id: event.data.message_id }
    case 'tool_call': {
      const others = answer.tools.filter((call) => call.tool !== event.data.tool)
      return { ...answer, tools: [...others, event.data] }
    }
    case 'delta':
      return { ...answer, content: answer.content + event.data.text }
    case 'record_ref':
      return { ...answer, refs: [...answer.refs, event.data] }
    case 'message_end':
      return { ...answer, status: event.data.status }
    case 'error':
      return { ...answer, status: 'failed', errorCode: event.data.code }
  }
}

function sameRecord(a: RecordContext | null, b: RecordContext | null): boolean {
  return a?.entity_type === b?.entity_type && a?.entity_id === b?.entity_id
}

/** The chat drawer (FR-AI-01..04): conversation, history, record context, drafts. */
export function AssistantPanel({ remaining, onClose }: { remaining: number; onClose: () => void }) {
  const { t } = useTranslation('assistant')
  const queryClient = useQueryClient()
  const inView = useRecordInView()
  const [view, setView] = useState<'chat' | 'history'>('chat')
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [live, setLive] = useState<LiveTurn | null>(null)
  const [draft, setDraft] = useState('')
  const [useContext, setUseContext] = useState(true)
  const conversation = useConversation(conversationId)
  const { create, stop } = useAssistantMutations()
  const input = useRef<HTMLTextAreaElement>(null)
  const end = useRef<HTMLDivElement>(null)
  const streaming = live?.answer.status === 'streaming'

  useEffect(() => {
    input.current?.focus()
  }, [view])
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' })
  }, [live, conversation.data])

  const conversationContext = conversation.data?.context ?? null
  const offered = inView && !sameRecord(inView, conversationContext) ? inView : null
  const context = conversationContext ?? (offered && useContext ? offered : null)

  async function send() {
    const question = draft.trim()
    if (!question || streaming) return
    const turn: LiveTurn = {
      question,
      before: conversationId === null ? 0 : (conversation.data?.messages.length ?? 0),
      answer: {
        id: null,
        role: 'assistant',
        content: '',
        status: 'streaming',
        errorCode: null,
        tools: [],
        refs: [],
      },
    }
    setDraft('')
    setLive(turn)
    const update = (event: StreamEvent) => {
      setLive((current) =>
        current ? { ...current, answer: applyEvent(current.answer, event) } : current,
      )
    }
    try {
      let id = conversationId
      const withContext = offered && useContext ? offered : null
      if (id === null) {
        const created = await create.mutateAsync(withContext ? { context: withContext } : {})
        id = created.id
        setConversationId(id)
      }
      const body =
        withContext && conversationId !== null
          ? { content: question, context: withContext }
          : { content: question }
      await streamMessage(id, body, update)
      await queryClient.invalidateQueries({ queryKey: ASSISTANT_KEY })
      setLive(null)
    } catch (error) {
      update({
        event: 'error',
        data: { code: error instanceof ApiError ? error.code : 'assistant.provider_unavailable' },
      })
    }
  }

  const all = (conversation.data?.messages ?? []).map(stored)
  const messages = live ? all.slice(0, live.before) : all
  // One keyed list for stored and live messages: when the turn ends and the stored copy
  // replaces the live answer, it keeps its key, so the message keeps its state (an open
  // "save as note" form is not lost to the refresh).
  const shown: { key: string; message: ShownMessage }[] = messages.map((message) => ({
    key: message.id ?? '',
    message,
  }))
  if (live) {
    shown.push(
      {
        key: 'live-question',
        message: {
          id: null,
          role: 'user',
          content: live.question,
          status: 'complete',
          errorCode: null,
          tools: [],
          refs: [],
        },
      },
      { key: live.answer.id ?? 'live-answer', message: live.answer },
    )
  }
  return (
    <aside
      id="assistant-panel"
      aria-label={t('title')}
      className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l bg-background shadow-xl sm:w-[28rem]"
      onKeyDown={(event) => {
        if (event.key === 'Escape') onClose()
      }}
    >
      <header className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <h2 className="font-semibold">{t('title')}</h2>
        <div className="flex gap-1">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={streaming}
            onClick={() => {
              setConversationId(null)
              setLive(null)
              setView('chat')
            }}
          >
            {t('newConversation')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={streaming}
            onClick={() => {
              setView(view === 'chat' ? 'history' : 'chat')
            }}
          >
            {view === 'chat' ? t('history') : t('backToChat')}
          </Button>
          <Button type="button" size="sm" variant="ghost" aria-label={t('close')} onClick={onClose}>
            {t('closeSymbol')}
          </Button>
        </div>
      </header>

      {view === 'history' ? (
        <History
          current={conversationId}
          onOpen={(id) => {
            setConversationId(id)
            setLive(null)
            setView('chat')
          }}
          onDeleted={(id) => {
            if (id === conversationId) setConversationId(null)
          }}
        />
      ) : (
        <>
          <div className="flex-1 overflow-y-auto px-3 py-3">
            {messages.length === 0 && !live ? (
              <p className="text-sm text-muted-foreground">{t('intro')}</p>
            ) : null}
            <ol role="log" aria-busy={streaming} className="space-y-3">
              {shown.map(({ key, message }) => (
                <AssistantMessage key={key} message={message} context={context} />
              ))}
            </ol>
            <div ref={end} />
          </div>

          <form
            className="space-y-2 border-t px-3 py-2"
            onSubmit={(event) => {
              event.preventDefault()
              void send()
            }}
          >
            {offered ? (
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={useContext}
                  onChange={(event) => {
                    setUseContext(event.target.checked)
                  }}
                />
                {t(`context.${offered.entity_type}`)}
              </label>
            ) : null}
            <Textarea
              ref={input}
              aria-label={t('input')}
              value={draft}
              rows={3}
              maxLength={MAX_CHARS}
              onChange={(event) => {
                setDraft(event.target.value)
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void send()
                }
              }}
            />
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                {draft.length > MAX_CHARS - 500
                  ? t('characters', { count: draft.length })
                  : t('budget', { count: remaining })}
              </p>
              {streaming ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!live.answer.id || conversationId === null}
                  onClick={() => {
                    if (live.answer.id && conversationId)
                      stop.mutate({ conversationId, messageId: live.answer.id })
                  }}
                >
                  {t('stop')}
                </Button>
              ) : (
                <Button type="submit" size="sm" disabled={draft.trim() === ''}>
                  {t('send')}
                </Button>
              )}
            </div>
          </form>
        </>
      )}
    </aside>
  )
}

function History({
  current,
  onOpen,
  onDeleted,
}: {
  current: string | null
  onOpen: (id: string) => void
  onDeleted: (id: string) => void
}) {
  const { t } = useTranslation('assistant')
  const { t: tc } = useTranslation()
  const locale = useLocale()
  const conversations = useConversations(true)
  const { rename, remove } = useAssistantMutations()
  const [editing, setEditing] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const items = conversations.data?.items ?? []
  return (
    <div className="flex-1 overflow-y-auto px-3 py-3">
      {conversations.isSuccess && items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('noConversations')}</p>
      ) : null}
      <ul className="space-y-2" aria-label={t('history')}>
        {items.map((item) => (
          <li
            key={item.id}
            className={`rounded-lg border p-2 ${item.id === current ? 'border-primary' : ''}`}
          >
            {editing === item.id ? (
              <form
                className="flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  rename.mutate(
                    { id: item.id, title: title.trim() },
                    {
                      onSuccess: () => {
                        setEditing(null)
                      },
                    },
                  )
                }}
              >
                <Input
                  aria-label={t('renameLabel')}
                  value={title}
                  maxLength={200}
                  onChange={(event) => {
                    setTitle(event.target.value)
                  }}
                />
                <Button type="submit" size="sm" disabled={title.trim() === ''}>
                  {tc('actions.save')}
                </Button>
              </form>
            ) : (
              <button
                type="button"
                className="block w-full text-left text-sm font-medium hover:underline"
                onClick={() => {
                  onOpen(item.id)
                }}
              >
                {item.title ?? t('untitled')}
              </button>
            )}
            <div className="mt-1 flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">
                {formatDateTime(item.updated_at, locale)}
              </span>
              <span className="flex gap-1">
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  onClick={() => {
                    setEditing(item.id)
                    setTitle(item.title ?? '')
                  }}
                >
                  {t('rename')}
                </Button>
                <ConfirmButton
                  label={t('delete')}
                  title={t('deleteTitle')}
                  description={t('deleteDescription')}
                  variant="destructive"
                  onConfirm={() => {
                    remove.mutate(item.id, {
                      onSuccess: () => {
                        onDeleted(item.id)
                      },
                    })
                  }}
                />
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
