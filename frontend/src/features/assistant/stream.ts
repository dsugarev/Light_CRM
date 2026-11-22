import { ApiError, type Schemas } from '@/api/client'

// The answer to a message arrives as Server-Sent Events (API spec 17). EventSource
// cannot POST, so the response body is read and parsed here. Everything else in
// the assistant goes through the generated client and TanStack Query.

export interface RecordRef {
  entity_type: string
  entity_id: string
  label: string
}

export type StreamEvent =
  | { event: 'message_start'; data: { message_id: string; conversation_id: string } }
  | { event: 'tool_call'; data: { tool: string; status: 'running' | 'done' } }
  | { event: 'delta'; data: { text: string } }
  | { event: 'record_ref'; data: RecordRef }
  | { event: 'action_proposed'; data: Schemas['ActionOut'] }
  | {
      event: 'message_end'
      data: {
        prompt_tokens: number
        completion_tokens: number
        remaining_budget: number
        status: 'complete' | 'stopped'
      }
    }
  | { event: 'error'; data: { code: string } }

/** Split a buffer into complete SSE blocks; returns the events and the unfinished rest. */
export function parseEvents(buffer: string): { events: StreamEvent[]; rest: string } {
  const blocks = buffer.split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: StreamEvent[] = []
  for (const block of blocks) {
    let name = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) name = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (data.length === 0) continue
    events.push({ event: name, data: JSON.parse(data.join('\n')) as unknown } as StreamEvent)
  }
  return { events, rest }
}

/** Send a message and call `onEvent` for each event until the stream ends. A refusal
 * before the stream starts (rate limit, budget, validation) throws an ApiError. */
export async function streamMessage(
  conversationId: string,
  body: Schemas['MessageCreate'],
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await globalThis.fetch(
    `${globalThis.location.origin}/api/v1/assistant/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify(body),
      signal: signal ?? null,
    },
  )
  if (!response.ok || !response.body) {
    const problem = (await response.json().catch(() => ({}))) as { code?: string }
    throw new ApiError(response.status, problem)
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const parsed = parseEvents(buffer)
    buffer = parsed.rest
    parsed.events.forEach(onEvent)
  }
  parseEvents(`${buffer}\n\n`).events.forEach(onEvent)
}
