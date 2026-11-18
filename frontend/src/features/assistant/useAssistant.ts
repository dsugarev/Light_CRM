import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router'

import { api, asPage, call, type Schemas } from '@/api/client'

export type RecordContext = Schemas['RecordContext']
export type Conversation = Schemas['ConversationOut']
export type ChatMessage = Schemas['MessageOut']

export const ASSISTANT_KEY = ['assistant'] as const

/** FR-AI-07: whether the assistant is on, and the caller's remaining daily budget. */
export function useAssistantStatus(signedIn: boolean) {
  return useQuery({
    queryKey: [...ASSISTANT_KEY, 'status'],
    queryFn: () => call(api.GET('/api/v1/assistant/status')),
    enabled: signedIn,
    staleTime: 60_000,
  })
}

export function useConversations(enabled: boolean) {
  return useQuery({
    queryKey: [...ASSISTANT_KEY, 'conversations'],
    queryFn: async () =>
      asPage(
        await call(
          api.GET('/api/v1/assistant/conversations', { params: { query: { page_size: 50 } } }),
        ),
      ),
    enabled,
  })
}

export function useConversation(conversationId: string | null) {
  return useQuery({
    queryKey: [...ASSISTANT_KEY, 'conversation', conversationId],
    queryFn: () =>
      call(
        api.GET('/api/v1/assistant/conversations/{conversation_id}', {
          params: { path: { conversation_id: conversationId ?? '' } },
        }),
      ),
    enabled: conversationId !== null,
  })
}

export function useAssistantMutations() {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: ASSISTANT_KEY })
  return {
    create: useMutation({
      mutationFn: (body: Schemas['ConversationCreate']) =>
        call(api.POST('/api/v1/assistant/conversations', { body })),
    }),
    rename: useMutation({
      mutationFn: ({ id, title }: { id: string; title: string }) =>
        call(
          api.PATCH('/api/v1/assistant/conversations/{conversation_id}', {
            params: { path: { conversation_id: id } },
            body: { title },
          }),
        ),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        call(
          api.DELETE('/api/v1/assistant/conversations/{conversation_id}', {
            params: { path: { conversation_id: id } },
          }),
        ),
      onSuccess: refresh,
    }),
    stop: useMutation({
      mutationFn: ({ conversationId, messageId }: { conversationId: string; messageId: string }) =>
        call(
          api.POST('/api/v1/assistant/conversations/{conversation_id}/messages/{message_id}/stop', {
            params: { path: { conversation_id: conversationId, message_id: messageId } },
          }),
        ),
    }),
    saveAsNote: useMutation({
      mutationFn: ({ messageId, body }: { messageId: string; body: Schemas['SaveAsNote'] }) =>
        call(
          api.POST('/api/v1/assistant/messages/{message_id}/save-as-note', {
            params: { path: { message_id: messageId } },
            body,
          }),
        ),
      // The note appears on the record's timeline (FR-ACT-03).
      onSuccess: () => queryClient.invalidateQueries({ queryKey: ['timeline'] }),
    }),
  }
}

const CONTEXT_PAGES: [RegExp, RecordContext['entity_type']][] = [
  [/^\/leads\/([0-9a-f-]{36})$/, 'lead'],
  [/^\/opportunities\/([0-9a-f-]{36})$/, 'opportunity'],
  [/^\/organizations\/([0-9a-f-]{36})$/, 'organization'],
]

/** FR-AI-03: the record whose page is open, offered as context. */
export function useRecordInView(): RecordContext | null {
  const { pathname } = useLocation()
  for (const [pattern, entityType] of CONTEXT_PAGES) {
    const match = pattern.exec(pathname)
    if (match?.[1]) return { entity_type: entityType, entity_id: match[1] }
  }
  return null
}

const PATHS: Record<string, string> = {
  lead: '/leads/',
  opportunity: '/opportunities/',
  organization: '/organizations/',
  contact: '/contacts/',
}

export function recordPath(entityType: string, entityId: string): string | null {
  const prefix = PATHS[entityType]
  return prefix ? `${prefix}${entityId}` : null
}

/** In-app links the assistant may produce; anything else is shown as plain text. */
export function isRecordLink(href: string): boolean {
  return /^\/(leads|opportunities|organizations|contacts)\/[0-9a-f-]{36}$/.test(href)
}
