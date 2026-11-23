import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import type { Schemas } from '@/api/client'
import {
  OPPORTUNITY,
  opportunityLists,
  REP_ME,
  signedInAs,
  USER,
  type ADMIN_ME,
} from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { problem, server } from '@/test/server'

import { parseEvents } from './stream'

// FR-AI-01..08 in the browser. The answer stream is served by MSW in the Server-Sent
// Events format of API spec 17; held streams let tests look at an answer in progress.

const CONVERSATION: Schemas['ConversationOut'] = {
  id: '01930000-0000-7000-8000-00000000a1c1',
  title: null,
  context: null,
  created_at: '2026-11-18T09:00:00Z',
  updated_at: '2026-11-18T09:00:00Z',
}
const MESSAGE_ID = '01930000-0000-7000-8000-00000000a1m2'

type Event = [string, unknown]

function sseBody(events: Event[]): string {
  return events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join('')
}

function sse(events: Event[]) {
  return new HttpResponse(sseBody(events), { headers: { 'Content-Type': 'text/event-stream' } })
}

/** A stream that sends `first`, then waits for `release()` before sending `rest`. */
function heldStream(first: Event[], rest: Event[]) {
  let release: (value: undefined) => void = () => undefined
  const gate = new Promise<undefined>((resolve) => {
    release = resolve
  })
  const encoder = new TextEncoder()
  const response = () =>
    new HttpResponse(
      new ReadableStream<Uint8Array>({
        async start(controller) {
          controller.enqueue(encoder.encode(sseBody(first)))
          await gate
          controller.enqueue(encoder.encode(sseBody(rest)))
          controller.close()
        },
      }),
      { headers: { 'Content-Type': 'text/event-stream' } },
    )
  return {
    response,
    release: () => {
      release(undefined)
    },
  }
}

const START: Event = ['message_start', { message_id: MESSAGE_ID, conversation_id: CONVERSATION.id }]
const END: Event = [
  'message_end',
  { prompt_tokens: 120, completion_tokens: 30, remaining_budget: 199850, status: 'complete' },
]

function assistantOn(me: typeof ADMIN_ME = REP_ME) {
  signedInAs(me)
  server.use(
    http.get('*/api/v1/assistant/status', () =>
      HttpResponse.json({
        enabled: true,
        daily_token_budget: 200000,
        used_today: 150,
        remaining_budget: 199850,
      }),
    ),
  )
}

/** Conversation endpoints; `stored` is what GET returns after the answer. */
function conversationApi(stored: Schemas['MessageOut'][] = []) {
  const created: unknown[] = []
  server.use(
    http.post('*/api/v1/assistant/conversations', async ({ request }) => {
      created.push(await request.json())
      return HttpResponse.json(CONVERSATION, { status: 201 })
    }),
    http.get(`*/api/v1/assistant/conversations/${CONVERSATION.id}`, () =>
      HttpResponse.json({ ...CONVERSATION, messages: stored }),
    ),
  )
  return created
}

function storedPair(
  question: string,
  answer: string,
  refs: Schemas['RecordRef'][] = [],
): [Schemas['MessageOut'], Schemas['MessageOut']] {
  const base = {
    status: 'complete' as const,
    error_code: null,
    tools_used: [],
    record_refs: [],
    prompt_tokens: 0,
    completion_tokens: 0,
    created_at: '2026-11-18T09:00:01Z',
  }
  return [
    {
      ...base,
      id: '01930000-0000-7000-8000-00000000a1m1',
      role: 'user' as const,
      content: question,
    },
    {
      ...base,
      id: MESSAGE_ID,
      role: 'assistant' as const,
      content: answer,
      tools_used: ['search_opportunities'],
      record_refs: refs,
      prompt_tokens: 120,
      completion_tokens: 30,
    },
  ]
}

async function openAssistant() {
  await userEvent.click(await screen.findByRole('button', { name: 'Assistant' }))
  return screen.getByRole('complementary', { name: 'Assistant' })
}

async function ask(panel: HTMLElement, question: string) {
  await userEvent.type(within(panel).getByRole('textbox', { name: 'Your question' }), question)
  await userEvent.click(within(panel).getByRole('button', { name: 'Send' }))
}

describe('FR-AI-07 switch', () => {
  it('shows no assistant while it is switched off', async () => {
    signedInAs(REP_ME)
    await renderApp('/search')
    expect(await screen.findByRole('link', { name: 'Leads' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Assistant' })).not.toBeInTheDocument()
  })

  it('opens the drawer from the header, in Bulgarian too', async () => {
    assistantOn({ ...REP_ME, locale: 'bg' })
    await renderApp('/search', 'bg')
    await userEvent.click(await screen.findByRole('button', { name: 'Асистент' }))
    const panel = screen.getByRole('complementary', { name: 'Асистент' })
    expect(
      within(panel).getByText(/Нищо не се променя, докато не я потвърдите/),
    ).toBeInTheDocument()
    expect(within(panel).getByText('Остават 199850 токена за днес')).toBeInTheDocument()
    await userEvent.click(within(panel).getByRole('button', { name: 'Затвори асистента' }))
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  })
})

describe('FR-AI-01, 02 streamed answers', () => {
  it('streams an answer with tool progress, Markdown, record links and no raw HTML', async () => {
    assistantOn()
    const link = `/opportunities/${OPPORTUNITY.id}`
    const answer =
      `You have **one** open deal: [${OPPORTUNITY.name}](${link}).\n\n` +
      '| Stage | Value |\n|---|---:|\n| Prospecting | 48000.00 |\n\n' +
      'See [elsewhere](https://evil.example.test/x) <img src="x" alt="injected"> <b>raw</b>'
    const refs = [
      { entity_type: 'opportunity', entity_id: OPPORTUNITY.id, label: OPPORTUNITY.name },
    ]
    const created = conversationApi(storedPair('Which deals are open?', answer, refs))
    const held = heldStream(
      [START, ['tool_call', { tool: 'pipeline_summary', status: 'running' }]],
      [
        ['tool_call', { tool: 'pipeline_summary', status: 'done' }],
        ['delta', { text: answer.slice(0, 20) }],
        ['delta', { text: answer.slice(20) }],
        ['record_ref', refs[0]],
        END,
      ],
    )
    let sent: unknown = null
    server.use(
      http.post(
        `*/api/v1/assistant/conversations/${CONVERSATION.id}/messages`,
        async ({ request }) => {
          sent = await request.json()
          return held.response()
        },
      ),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await ask(panel, 'Which deals are open?')

    expect(await within(panel).findByText('Summing up the pipeline…')).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: 'Stop' })).toBeInTheDocument()
    held.release()

    // Linked in the answer and again under "Records mentioned".
    const deals = await within(panel).findAllByRole('link', { name: OPPORTUNITY.name })
    expect(deals.map((a) => a.getAttribute('href'))).toEqual([link, link])
    expect(within(panel).getByRole('table')).toHaveTextContent('Prospecting48000.00')
    expect(within(panel).getByText('one').tagName).toBe('STRONG')
    // External links stay text; images and raw HTML are never rendered.
    expect(within(panel).queryByRole('link', { name: 'elsewhere' })).not.toBeInTheDocument()
    expect(within(panel).getByText('elsewhere')).toBeInTheDocument()
    expect(panel.querySelector('img')).toBeNull()
    expect(panel.querySelector('b')).toBeNull()
    expect(within(panel).getByText('Records mentioned')).toBeInTheDocument()
    expect(created).toEqual([{}])
    expect(sent).toEqual({ content: 'Which deals are open?' })
    expect(await within(panel).findByRole('button', { name: 'Send' })).toBeInTheDocument()
  })

  it('stops a running answer', async () => {
    assistantOn()
    conversationApi()
    const held = heldStream(
      [START, ['delta', { text: 'Partial' }]],
      [['message_end', { ...(END[1] as object), status: 'stopped' }]],
    )
    let stopped = false
    server.use(
      http.post(`*/api/v1/assistant/conversations/${CONVERSATION.id}/messages`, () =>
        held.response(),
      ),
      http.post(
        `*/api/v1/assistant/conversations/${CONVERSATION.id}/messages/${MESSAGE_ID}/stop`,
        () => {
          stopped = true
          held.release()
          return new HttpResponse(null, { status: 204 })
        },
      ),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await ask(panel, 'Tell me everything')
    expect(await within(panel).findByText('Partial')).toBeInTheDocument()
    await userEvent.click(within(panel).getByRole('button', { name: 'Stop' }))
    await waitFor(() => {
      expect(stopped).toBe(true)
    })
  })

  it('FR-AI-07 shows a provider failure as a chat error', async () => {
    assistantOn()
    conversationApi()
    const held = heldStream([START, ['error', { code: 'assistant.provider_unavailable' }]], [])
    server.use(
      http.post(`*/api/v1/assistant/conversations/${CONVERSATION.id}/messages`, () =>
        held.response(),
      ),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await ask(panel, 'Anything')
    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      'The assistant is not available right now.',
    )
    held.release()
  })

  it('FR-AI-08 shows a used-up budget', async () => {
    assistantOn()
    conversationApi()
    server.use(
      http.post(`*/api/v1/assistant/conversations/${CONVERSATION.id}/messages`, () =>
        problem(429, 'assistant.budget_exceeded'),
      ),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await ask(panel, 'One more')
    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      "You have used today's assistant budget.",
    )
  })
})

describe('FR-AI-01 follow-up questions', () => {
  it('shows each message once while a follow-up streams', async () => {
    assistantOn()
    const earlier = storedPair('First question', 'First answer')
    let messages: Schemas['MessageOut'][] = earlier
    server.use(
      http.get('*/api/v1/assistant/conversations', () =>
        HttpResponse.json({ items: [CONVERSATION], total: 1, page: 1, page_size: 50 }),
      ),
      http.get(`*/api/v1/assistant/conversations/${CONVERSATION.id}`, () =>
        HttpResponse.json({ ...CONVERSATION, messages }),
      ),
    )
    const held = heldStream([START, ['delta', { text: 'Second answer' }]], [END])
    let body: unknown = null
    server.use(
      http.post(
        `*/api/v1/assistant/conversations/${CONVERSATION.id}/messages`,
        async ({ request }) => {
          body = await request.json()
          // The server stores the question and the unfinished answer before streaming.
          const [question, answer] = storedPair('Second question', '')
          messages = [
            ...earlier,
            { ...question, id: 'q2' },
            { ...answer, id: 'a2', status: 'streaming', content: '' },
          ]
          return held.response()
        },
      ),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await userEvent.click(within(panel).getByRole('button', { name: 'Conversations' }))
    await userEvent.click(
      await within(panel).findByRole('button', { name: 'Untitled conversation' }),
    )
    expect(await within(panel).findByText('First answer')).toBeInTheDocument()
    await ask(panel, 'Second question')
    expect(await within(panel).findByText('Second answer')).toBeInTheDocument()
    expect(within(panel).getAllByText('Second question')).toHaveLength(1)
    expect(within(panel).getAllByText('First question')).toHaveLength(1)
    expect(body).toEqual({ content: 'Second question' })
    held.release()
  })
})

describe('FR-AI-03 record context', () => {
  it('offers the opportunity in view and sends it with the new conversation', async () => {
    assistantOn()
    opportunityLists()
    server.use(
      http.get(`*/api/v1/opportunities/${OPPORTUNITY.id}`, () => HttpResponse.json(OPPORTUNITY)),
      http.get(`*/api/v1/opportunities/${OPPORTUNITY.id}/stage-history`, () =>
        HttpResponse.json([]),
      ),
    )
    const created = conversationApi()
    server.use(
      http.post(`*/api/v1/assistant/conversations/${CONVERSATION.id}/messages`, () =>
        sse([START, ['delta', { text: 'Dear customer' }], END]),
      ),
    )
    await renderApp(`/opportunities/${OPPORTUNITY.id}`)
    const panel = await openAssistant()
    const offer = within(panel).getByRole('checkbox', { name: 'Ask about this opportunity' })
    expect(offer).toBeChecked()
    await ask(panel, 'Draft a follow-up')
    await waitFor(() => {
      expect(created).toEqual([
        { context: { entity_type: 'opportunity', entity_id: OPPORTUNITY.id } },
      ])
    })
  })
})

describe('FR-AI-01 history', () => {
  it('lists, opens, renames and deletes conversations', async () => {
    assistantOn()
    const titled = { ...CONVERSATION, title: 'Pipeline review' }
    let renamed: unknown = null
    let deleted = false
    server.use(
      http.get('*/api/v1/assistant/conversations', () =>
        HttpResponse.json({ items: deleted ? [] : [titled], total: 1, page: 1, page_size: 50 }),
      ),
      http.get(`*/api/v1/assistant/conversations/${CONVERSATION.id}`, () =>
        HttpResponse.json({ ...titled, messages: storedPair('Pipeline?', 'It is **fine**.') }),
      ),
      http.patch(`*/api/v1/assistant/conversations/${CONVERSATION.id}`, async ({ request }) => {
        renamed = await request.json()
        return HttpResponse.json({ ...titled, title: 'Q4 review' })
      }),
      http.delete(`*/api/v1/assistant/conversations/${CONVERSATION.id}`, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await userEvent.click(within(panel).getByRole('button', { name: 'Conversations' }))
    await userEvent.click(await within(panel).findByRole('button', { name: 'Pipeline review' }))
    expect(await within(panel).findByText('Pipeline?')).toBeInTheDocument()
    expect(within(panel).getByText('fine').tagName).toBe('STRONG')

    await userEvent.click(within(panel).getByRole('button', { name: 'Conversations' }))
    await userEvent.click(await within(panel).findByRole('button', { name: 'Rename' }))
    const title = within(panel).getByRole('textbox', { name: 'Conversation title' })
    await userEvent.clear(title)
    await userEvent.type(title, 'Q4 review')
    await userEvent.click(within(panel).getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      expect(renamed).toEqual({ title: 'Q4 review' })
    })

    await userEvent.click(within(panel).getByRole('button', { name: 'Delete' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }))
    expect(await within(panel).findByText('No conversations yet.')).toBeInTheDocument()
  })
})

describe('FR-AI-04 drafts', () => {
  function withDraft() {
    const refs = [
      { entity_type: 'opportunity', entity_id: OPPORTUNITY.id, label: OPPORTUNITY.name },
    ]
    server.use(
      http.get('*/api/v1/assistant/conversations', () =>
        HttpResponse.json({ items: [CONVERSATION], total: 1, page: 1, page_size: 50 }),
      ),
      http.get(`*/api/v1/assistant/conversations/${CONVERSATION.id}`, () =>
        HttpResponse.json({
          ...CONVERSATION,
          messages: storedPair('Draft a follow-up', 'Dear Ms Petrova,\n\nThank you.', refs),
        }),
      ),
    )
  }

  async function openDraft() {
    await renderApp('/search')
    const panel = await openAssistant()
    await userEvent.click(within(panel).getByRole('button', { name: 'Conversations' }))
    await userEvent.click(
      await within(panel).findByRole('button', { name: 'Untitled conversation' }),
    )
    await within(panel).findByText('Thank you.')
    return panel
  }

  it('copies a draft and saves an edited draft as a note on a cited record', async () => {
    assistantOn()
    withDraft()
    const writeText = vi.fn(() => Promise.resolve())
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    let saved: unknown = null
    server.use(
      http.post(`*/api/v1/assistant/messages/${MESSAGE_ID}/save-as-note`, async ({ request }) => {
        saved = await request.json()
        return HttpResponse.json({}, { status: 201 })
      }),
    )
    const panel = await openDraft()
    await userEvent.click(within(panel).getByRole('button', { name: 'Copy' }))
    expect(writeText).toHaveBeenCalledWith('Dear Ms Petrova,\n\nThank you.')
    expect(await within(panel).findByRole('button', { name: 'Copied' })).toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: 'Save as note' }))
    const form = within(panel).getByRole('form', { name: 'Save as note' })
    expect(within(form).getByRole('combobox', { name: 'Record' })).toHaveDisplayValue(
      `Opportunity: ${OPPORTUNITY.name}`,
    )
    const text = within(form).getByRole('textbox', { name: 'Note text' })
    await userEvent.type(text, ' Best regards.')
    await userEvent.click(within(form).getByRole('button', { name: 'Save note' }))
    await waitFor(() => {
      expect(saved).toEqual({
        entity_type: 'opportunity',
        entity_id: OPPORTUNITY.id,
        content: 'Dear Ms Petrova,\n\nThank you. Best regards.',
      })
    })
    expect(await screen.findByText('Saved as a note on the record.')).toBeInTheDocument()
  })

  it('offers no note saving to viewers', async () => {
    assistantOn({
      ...REP_ME,
      role: 'viewer',
      full_name: USER.full_name,
      permissions: ['records.read'],
    })
    withDraft()
    const panel = await openDraft()
    expect(within(panel).getByRole('button', { name: 'Copy' })).toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Save as note' })).not.toBeInTheDocument()
  })
})

describe('Server-Sent Events parsing', () => {
  it('keeps an unfinished block for the next chunk', () => {
    const first = parseEvents('event: delta\ndata: {"text":"Hel"}\n\nevent: delta\ndata: {"te')
    expect(first.events).toEqual([{ event: 'delta', data: { text: 'Hel' } }])
    const second = parseEvents(`${first.rest}xt":"lo"}\n\n`)
    expect(second.events).toEqual([{ event: 'delta', data: { text: 'lo' } }])
    expect(second.rest).toBe('')
  })
})

describe('FR-AI-04 save as note right after an answer', () => {
  it('keeps an opened note form when the stored conversation replaces the live answer', async () => {
    assistantOn()
    const answer = `Your open deal is ${OPPORTUNITY.name}.`
    const refs = [
      { entity_type: 'opportunity', entity_id: OPPORTUNITY.id, label: OPPORTUNITY.name },
    ]
    conversationApi()
    // Hold the reload that follows the answer, so the live answer is still on screen.
    let releaseReload: (value: undefined) => void = () => undefined
    const reload = new Promise<undefined>((resolve) => {
      releaseReload = resolve
    })
    server.use(
      http.post(`*/api/v1/assistant/conversations/${CONVERSATION.id}/messages`, () =>
        sse([START, ['delta', { text: answer }], ['record_ref', refs[0]], END]),
      ),
      http.get(`*/api/v1/assistant/conversations/${CONVERSATION.id}`, async () => {
        await reload
        return HttpResponse.json({
          ...CONVERSATION,
          messages: storedPair('Which deals are open?', answer, refs),
        })
      }),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await ask(panel, 'Which deals are open?')
    await userEvent.click(await within(panel).findByRole('button', { name: 'Save as note' }))
    expect(within(panel).getByRole('form', { name: 'Save as note' })).toBeInTheDocument()

    releaseReload(undefined)
    await waitFor(() => {
      expect(within(panel).getByRole('button', { name: 'Send' })).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(within(panel).getAllByText(/Which deals are open\?/)).toHaveLength(1)
    })
    expect(within(panel).getByRole('form', { name: 'Save as note' })).toBeInTheDocument()
  })
})

// --- FR-AI-09 actions with confirmation (ADR 0030) ------------------------------------------

const ACTION: Schemas['ActionOut'] = {
  id: '01930000-0000-7000-8000-00000000ac01',
  action: 'activity.create',
  title: 'Create task',
  details: [
    { label: 'Subject', value: 'Call Mr Z' },
    { label: 'Due', value: '23 Nov 2026, 09:00' },
    { label: 'Linked to', value: 'Sunrise Foods OOD' },
  ],
  target: null,
  destructive: false,
  status: 'proposed',
  error_code: null,
  result: null,
  expires_at: '2099-01-01T00:00:00Z',
  created_at: '2026-11-22T09:00:00Z',
}

function actionStream(action: Schemas['ActionOut']) {
  const held = heldStream(
    [
      START,
      ['tool_call', { tool: 'propose_create_activity', status: 'running' }],
      ['tool_call', { tool: 'propose_create_activity', status: 'done' }],
      ['action_proposed', action],
      ['delta', { text: 'I prepared the task; please confirm it.' }],
    ],
    [END],
  )
  server.use(
    http.post(`*/api/v1/assistant/conversations/${CONVERSATION.id}/messages`, () =>
      held.response(),
    ),
  )
  return held
}

describe('FR-AI-09 actions with confirmation', () => {
  it('shows a proposed task as a card and creates it only on Confirm', async () => {
    assistantOn()
    conversationApi()
    const held = actionStream(ACTION)
    let confirmed = 0
    server.use(
      http.post(`*/api/v1/assistant/actions/${ACTION.id}/confirm`, () => {
        confirmed += 1
        return HttpResponse.json({
          action: {
            ...ACTION,
            status: 'confirmed',
            result: {
              entity_type: 'activity',
              entity_id: '01930000-0000-7000-8000-00000000ac02',
              label: 'Call Mr Z',
              url: '/tasks',
            },
          },
          set_password: null,
        })
      }),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await ask(panel, 'Create a task due tomorrow: Call Mr Z')
    const card = await within(panel).findByRole('region', { name: 'Create task' })
    expect(within(card).getByText('Call Mr Z')).toBeInTheDocument()
    expect(within(card).getByText('Nothing changes until you confirm.')).toBeInTheDocument()
    expect(confirmed).toBe(0)
    await userEvent.click(within(card).getByRole('button', { name: 'Confirm' }))
    expect(await within(card).findByText('Done.')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Open Call Mr Z' })).toHaveAttribute(
      'href',
      '/tasks',
    )
    expect(confirmed).toBe(1)
    expect(within(card).queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
    held.release()
  })

  it('cancels a card, and shows a refused confirmation as an error', async () => {
    assistantOn()
    conversationApi()
    const held = actionStream({ ...ACTION, destructive: true, title: 'Archive opportunity' })
    server.use(
      http.post(`*/api/v1/assistant/actions/${ACTION.id}/confirm`, () =>
        problem(409, 'conflict.version_mismatch'),
      ),
      http.post(
        `*/api/v1/assistant/actions/${ACTION.id}/cancel`,
        () => new HttpResponse(null, { status: 204 }),
      ),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await ask(panel, 'Archive it')
    const card = await within(panel).findByRole('region', { name: 'Archive opportunity' })
    expect(card).toHaveAttribute('data-status', 'proposed')
    expect(
      within(card).getByText('This changes or removes data. Check it, then confirm.'),
    ).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: 'Confirm' }))
    expect(await within(card).findByRole('alert')).toBeInTheDocument()
    expect(within(card).getByText('Not done.')).toBeInTheDocument()
    held.release()
  })

  it('shows a new user’s one-time link once after confirming', async () => {
    assistantOn()
    conversationApi()
    const create: Schemas['ActionOut'] = { ...ACTION, action: 'user.create', title: 'Create user' }
    const held = actionStream(create)
    server.use(
      http.post(`*/api/v1/assistant/actions/${ACTION.id}/confirm`, () =>
        HttpResponse.json({
          action: {
            ...create,
            status: 'confirmed',
            result: {
              entity_type: 'user',
              entity_id: '01930000-0000-7000-8000-00000000ac03',
              label: 'Nova Kolega',
              url: '/admin/users/01930000-0000-7000-8000-00000000ac03',
            },
          },
          set_password: {
            url: 'https://crm.example/set-password#token=abc',
            expires_at: '2026-11-25T09:00:00Z',
            emailed: false,
          },
        }),
      ),
    )
    await renderApp('/search')
    const panel = await openAssistant()
    await ask(panel, 'Create a user')
    const card = await within(panel).findByRole('region', { name: 'Create user' })
    await userEvent.click(within(card).getByRole('button', { name: 'Confirm' }))
    expect(await within(card).findByTestId('password-link')).toBeInTheDocument()
    held.release()
  })
})
