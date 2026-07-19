import { QueryClient, QueryClientProvider } from '@tanstack/solid-query'
import { fireEvent, render, screen, waitFor } from '@solidjs/testing-library'
import { createSignal, Show } from 'solid-js'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ChatWorkspace } from '@/features/chat/ChatWorkspace'
import { ChatDraftProvider } from '@/features/chat/ChatDraftProvider'
import { changeLocale } from '@/shared/i18n/config'
import { I18nProvider } from '@/shared/i18n/I18nProvider'

afterEach(async () => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
  await changeLocale('en')
})

describe('chat workspace', () => {
  it('uses the selected locale for the assistant allowance', async () => {
    await changeLocale('ru')
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) =>
        Promise.resolve(
          String(input).endsWith('/users/me/agent/usage')
            ? jsonResponse({
                used: 0,
                access_level: 'limited',
                limit: 10,
                remaining: 10,
              })
            : jsonResponse({ chats: [], next_offset: null }),
        ),
      ),
    )
    renderChatWorkspace()

    expect(
      await screen.findByText('Доступно 10 из 10 запросов к ассистенту'),
    ).toBeVisible()
  })

  it('keeps the assistant available for unmetered accounts', async () => {
    await changeLocale('ru')
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) =>
        Promise.resolve(
          String(input).endsWith('/users/me/agent/usage')
            ? jsonResponse({
                used: 42,
                access_level: 'unmetered',
                limit: null,
                remaining: null,
              })
            : jsonResponse({ chats: [], next_offset: null }),
        ),
      ),
    )
    renderChatWorkspace()

    expect(
      await screen.findByText('Запросы к ассистенту без ограничений'),
    ).toBeVisible()
    expect(screen.getByRole('textbox')).toBeEnabled()
  })

  it('uses a dismissible conversation drawer on compact screens', async () => {
    vi.stubGlobal('matchMedia', createMatchMedia(true))
    const firstChat = createChat()
    const secondChat = {
      ...createChat(),
      chat_id: 'second-chat-id',
      title: 'Weekly planning',
      is_active: false,
    }
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (isChatListRequest(input)) {
          return Promise.resolve(
            jsonResponse({ chats: [firstChat, secondChat], next_offset: null }),
          )
        }
        if (url.includes('/messages')) {
          return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
        }
        if (url.endsWith(`/${secondChat.chat_id}/activate`) && init?.method === 'POST') {
          return Promise.resolve(jsonResponse({ ...secondChat, is_active: true }))
        }
        return Promise.resolve(jsonResponse(firstChat))
      }),
    )
    renderChatWorkspace()

    const drawer = await screen.findByLabelText('Conversations', {
      selector: 'aside',
    })
    await screen.findByText('Weekly planning')
    expect(drawer).toHaveAttribute('aria-hidden', 'true')
    await fireEvent.click(
      screen.getByRole('button', { name: 'Show conversations' }),
    )
    expect(drawer).not.toHaveAttribute('aria-hidden')
    await fireEvent.click(
      screen.getByRole('button', {
        name: 'Open conversation Weekly planning',
      }),
    )

    await waitFor(() => expect(drawer).toHaveAttribute('aria-hidden', 'true'))
  })

  it('loads additional conversations from the next server page', async () => {
    const recentChat = createChat()
    const olderChat = {
      ...createChat(),
      chat_id: 'older-chat-id',
      title: 'Archived planning',
      is_active: false,
      created_at: '2026-06-01T09:00:00',
    }
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const offset = chatListRequestOffset(input)
      if (offset === 0) {
        return Promise.resolve(
          jsonResponse({ chats: [recentChat], next_offset: 30 }),
        )
      }
      if (offset === 30) {
        return Promise.resolve(
          jsonResponse({ chats: [olderChat], next_offset: null }),
        )
      }
      return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderChatWorkspace()

    expect((await screen.findAllByText('Daily work')).length).toBeGreaterThan(0)
    await fireEvent.click(
      screen.getByRole('button', { name: 'Load more conversations' }),
    )

    expect(await screen.findByText('Archived planning')).toBeVisible()
    expect(
      screen.getByRole('button', { name: 'Open conversation Daily work' }),
    ).toBeVisible()
    expect(
      screen.queryByRole('button', { name: 'Load more conversations' }),
    ).not.toBeInTheDocument()
    expect(
      fetchMock.mock.calls
        .map(([input]) => chatListRequestOffset(input))
        .filter((offset) => offset !== undefined),
    ).toEqual([0, 30])
  })

  it('continues from the shifted offset after deleting a loaded conversation', async () => {
    const firstPage = Array.from({ length: 30 }, (_, index) => ({
      ...createChat(),
      chat_id: `chat-${index}`,
      title: `Conversation ${index}`,
      is_active: index === 0,
    }))
    const nextChat = {
      ...createChat(),
      chat_id: 'next-chat-id',
      title: 'Conversation from the next page',
      is_active: false,
    }
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const offset = chatListRequestOffset(input)
      if (offset === 0) {
        return Promise.resolve(
          jsonResponse({ chats: firstPage, next_offset: 30 }),
        )
      }
      if (offset === 29) {
        return Promise.resolve(
          jsonResponse({ chats: [nextChat], next_offset: null }),
        )
      }
      if (init?.method === 'DELETE') {
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderChatWorkspace()

    await screen.findByRole('button', {
      name: 'Open conversation Conversation 0',
    })
    await fireEvent.click(
      screen.getByRole('button', { name: 'Delete conversation' }),
    )
    await fireEvent.click(
      screen.getAllByRole('button', { name: 'Delete conversation' })[1],
    )
    await waitFor(() =>
      expect(
        screen.queryByRole('button', {
          name: 'Open conversation Conversation 0',
        }),
      ).not.toBeInTheDocument(),
    )
    await fireEvent.click(
      screen.getByRole('button', { name: 'Load more conversations' }),
    )

    expect(await screen.findByText(nextChat.title)).toBeVisible()
    expect(
      screen.queryByRole('button', {
        name: 'Open conversation Conversation 0',
      }),
    ).not.toBeInTheDocument()
    expect(
      fetchMock.mock.calls
        .map(([input]) => chatListRequestOffset(input))
        .filter((offset) => offset !== undefined),
    ).toEqual([0, 29])
  })

  it('continues after the shifted offset when a conversation is prepended', async () => {
    const firstPage = Array.from({ length: 30 }, (_, index) => ({
      ...createChat(),
      chat_id: `chat-${index}`,
      title: `Conversation ${index}`,
      is_active: index === 0,
    }))
    const createdChat = {
      ...createChat(),
      chat_id: 'created-chat-id',
      title: 'New chat',
      created_at: '2026-07-16T09:00:00',
    }
    const nextChat = {
      ...createChat(),
      chat_id: 'next-chat-id',
      title: 'First not-yet-loaded conversation',
      is_active: false,
    }
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const offset = chatListRequestOffset(input)
      if (offset === 0) {
        return Promise.resolve(
          jsonResponse({ chats: firstPage, next_offset: 30 }),
        )
      }
      if (offset === 31) {
        return Promise.resolve(
          jsonResponse({ chats: [nextChat], next_offset: null }),
        )
      }
      if (String(input) === '/api/v1/chats' && init?.method === 'POST') {
        return Promise.resolve(jsonResponse(createdChat, 201))
      }
      return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderChatWorkspace()

    await screen.findByRole('button', {
      name: 'Open conversation Conversation 0',
    })
    await fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
    await screen.findByRole('button', {
      name: 'Open conversation New chat',
    })
    await fireEvent.click(
      screen.getByRole('button', { name: 'Load more conversations' }),
    )

    expect(await screen.findByText(nextChat.title)).toBeVisible()
    expect(
      screen.getAllByRole('button', {
        name: 'Open conversation Conversation 29',
      }),
    ).toHaveLength(1)
    expect(
      fetchMock.mock.calls
        .map(([input]) => chatListRequestOffset(input))
        .filter((offset) => offset !== undefined),
    ).toEqual([0, 31])
  })

  it('activates an existing conversation without reloading the chat list', async () => {
    const firstChat = createChat()
    const secondChat = {
      ...createChat(),
      chat_id: 'second-chat-id',
      title: 'Weekly planning',
      is_active: false,
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (isChatListRequest(input)) {
        return Promise.resolve(
          jsonResponse({ chats: [firstChat, secondChat], next_offset: null }),
        )
      }
      if (url.includes('/messages')) {
        return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
      }
      if (
        url === `/api/v1/chats/${secondChat.chat_id}/activate` &&
        init?.method === 'POST'
      ) {
        return Promise.resolve(jsonResponse({ ...secondChat, is_active: true }))
      }
      return Promise.resolve(jsonResponse(firstChat))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderChatWorkspace()

    await screen.findByText('Weekly planning')
    await fireEvent.click(
      screen.getByRole('button', {
        name: 'Open conversation Weekly planning',
      }),
    )

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input) ===
              `/api/v1/chats/${secondChat.chat_id}/activate` &&
            init?.method === 'POST',
        ),
      ).toBe(true),
    )
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => isChatListRequest(input),
      ),
    ).toHaveLength(1)
  })

  it('adds a newly created conversation without reloading the chat list', async () => {
    const existingChat = createChat()
    const newChat = {
      ...createChat(),
      chat_id: 'new-chat-id',
      title: 'New chat',
      created_at: '2026-07-15T10:00:00',
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (isChatListRequest(input)) {
        return Promise.resolve(
          jsonResponse({ chats: [existingChat], next_offset: null }),
        )
      }
      if (url.includes('/messages')) {
        return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
      }
      if (url === '/api/v1/chats' && init?.method === 'POST') {
        return Promise.resolve(jsonResponse(newChat, 201))
      }
      return Promise.resolve(jsonResponse(existingChat))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderChatWorkspace()

    expect((await screen.findAllByText('Daily work')).length).toBeGreaterThan(0)
    await fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
    expect((await screen.findAllByText('New chat')).length).toBeGreaterThan(0)
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => isChatListRequest(input),
      ),
    ).toHaveLength(1)
  })

  it('shows agent plan progress and the persisted final response', async () => {
    const chat = createChat()
    let agentCompleted = false
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (isChatListRequest(input)) {
        return Promise.resolve(jsonResponse({ chats: [chat], next_offset: null }))
      }
      if (url.endsWith('/users/me/agent/usage')) {
        return Promise.resolve(
          jsonResponse(
            agentCompleted
              ? {
                  used: 7,
                  access_level: 'limited',
                  limit: 7,
                  remaining: 0,
                }
              : {
                  used: 6,
                  access_level: 'limited',
                  limit: 7,
                  remaining: 1,
                },
          ),
        )
      }
      if (url.includes(`/chats/${chat.chat_id}/messages`)) {
        return Promise.resolve(
          jsonResponse({
            messages: agentCompleted
              ? [
                  createMessage(chat.chat_id, 'user', 'What is due today?', 1),
                  createMessage(chat.chat_id, 'assistant', 'One task is due today.', 2),
                ]
              : [],
            next_offset: null,
          }),
        )
      }
      if (url === `/api/v1/chats/${chat.chat_id}/agent` && init?.method === 'POST') {
        return Promise.resolve(agentStreamResponse(() => (agentCompleted = true)))
      }
      return Promise.resolve(jsonResponse(chat))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderChatWorkspace()

    const composer = await findReadyComposer()
    expect(
      await screen.findByText('1 of 7 assistant request available'),
    ).toBeVisible()
    await fireEvent.input(composer, { target: { value: 'What is due today?' } })
    await fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    expect(await screen.findByText('Check today’s tasks')).toBeVisible()
    expect(screen.getByText('In progress')).toBeVisible()
    expect(await screen.findByText('One task is due today.')).toBeVisible()
    expect(
      await screen.findByText('The assistant request limit has been reached.'),
    ).toBeVisible()
    expect(composer).toBeDisabled()
    const agentCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).endsWith(`/chats/${chat.chat_id}/agent`) &&
        init?.method === 'POST',
    )
    expect(JSON.parse(String(agentCall?.[1]?.body))).toEqual({
      message: 'What is due today?',
    })
  })

  it('explains an unverified account limit without sending a request', async () => {
    const chat = createChat()
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (isChatListRequest(input)) {
        return Promise.resolve(jsonResponse({ chats: [chat], next_offset: null }))
      }
      if (url.endsWith('/users/me/agent/usage')) {
        return Promise.resolve(
          jsonResponse({
            used: 4,
            access_level: 'limited',
            limit: 4,
            remaining: 0,
          }),
        )
      }
      return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderChatWorkspace(false)

    const composer = await screen.findByRole('textbox', {
      name: /Ask about tasks/,
    })
    expect(
      await screen.findByText(
        'The assistant request limit has been reached. Verify your email to increase it.',
      ),
    ).toBeVisible()
    expect(composer).toBeDisabled()
    expect(
      fetchMock.mock.calls.some(([input]) => String(input).endsWith('/agent')),
    ).toBe(false)
  })

  it('keeps the draft when the assistant request is not accepted', async () => {
    const chat = createChat()
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (isChatListRequest(input)) {
          return Promise.resolve(jsonResponse({ chats: [chat], next_offset: null }))
        }
        if (url.includes(`/chats/${chat.chat_id}/messages`)) {
          return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
        }
        if (url === `/api/v1/chats/${chat.chat_id}/agent` && init?.method === 'POST') {
          return Promise.reject(new TypeError('Network unavailable'))
        }
        return Promise.resolve(jsonResponse(chat))
      }),
    )
    renderChatWorkspace()

    const composer = await findReadyComposer()
    await fireEvent.input(composer, { target: { value: 'Keep this request' } })
    await fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(composer).toBeEnabled())
    expect(composer).toHaveValue('Keep this request')
  })

  it('renames and deletes a conversation through confirmed actions', async () => {
    let chats = [createChat()]
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (isChatListRequest(input)) {
        return Promise.resolve(jsonResponse({ chats, next_offset: null }))
      }
      if (url.includes('/messages')) {
        return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
      }
      if (init?.method === 'PATCH') {
        chats = [{ ...chats[0], title: 'Planning' }]
        return Promise.resolve(jsonResponse(chats[0]))
      }
      if (init?.method === 'DELETE') {
        chats = []
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(jsonResponse(chats[0]))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderChatWorkspace()

    expect((await screen.findAllByText('Daily work')).length).toBeGreaterThan(0)
    await fireEvent.click(screen.getByRole('button', { name: 'Rename conversation' }))
    const titleInput = screen.getByRole('textbox', { name: 'Rename conversation' })
    await fireEvent.input(titleInput, { target: { value: 'Planning' } })
    await fireEvent.click(screen.getByRole('button', { name: 'Save title' }))
    expect((await screen.findAllByText('Planning')).length).toBeGreaterThan(0)

    const deleteButton = screen.getByRole('button', {
      name: 'Delete conversation',
    })
    await waitFor(() => expect(deleteButton).toBeEnabled())
    await fireEvent.click(deleteButton)
    expect(screen.getByText('Delete this conversation?')).toBeVisible()
    const listRequestCount = fetchMock.mock.calls.filter(
      ([input]) => isChatListRequest(input),
    ).length
    const deletedChatMessageRequestCount = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes(`/chats/${chats[0].chat_id}/messages`),
    ).length
    await fireEvent.click(
      screen.getAllByRole('button', { name: 'Delete conversation' })[1],
    )
    expect(
      (await screen.findAllByText('No conversations yet')).length,
    ).toBeGreaterThan(0)
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(
      true,
    )
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => isChatListRequest(input),
      ),
    ).toHaveLength(listRequestCount)
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).includes('/chats/chat-id/messages'),
      ),
    ).toHaveLength(deletedChatMessageRequestCount)
  })

  it('keeps a conversation draft when switching workspace presentation', async () => {
    const chat = createChat()
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (isChatListRequest(input)) {
          return Promise.resolve(jsonResponse({ chats: [chat], next_offset: null }))
        }
        return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
      }),
    )
    const queryClient = createTestQueryClient()
    const [showPage, setShowPage] = createSignal(false)
    render(() => (
      <ChatDraftProvider userId="user-id">
        <I18nProvider>
          <QueryClientProvider client={queryClient}>
            <button type="button" onClick={() => setShowPage(true)}>
              Open full chat
            </button>
            <Show
              when={showPage()}
              fallback={<ChatWorkspace emailVerified mode="panel" />}
            >
              <ChatWorkspace emailVerified mode="page" />
            </Show>
          </QueryClientProvider>
        </I18nProvider>
      </ChatDraftProvider>
    ))

    const panelComposer = await findReadyComposer()
    await fireEvent.input(panelComposer, {
      target: { value: 'Draft for this conversation' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Open full chat' }))

    expect(
      await screen.findByRole('textbox', { name: /Ask about tasks/ }),
    ).toHaveValue('Draft for this conversation')
  })

  it('restores a conversation draft after the application is reloaded', async () => {
    const chat = createChat()
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (isChatListRequest(input)) {
          return Promise.resolve(jsonResponse({ chats: [chat], next_offset: null }))
        }
        return Promise.resolve(jsonResponse({ messages: [], next_offset: null }))
      }),
    )
    const firstRender = renderChatWorkspace()

    const composer = await findReadyComposer()
    await fireEvent.input(composer, {
      target: { value: 'Draft kept during reload' },
    })
    firstRender.unmount()
    renderChatWorkspace()

    expect(await findReadyComposer()).toHaveValue('Draft kept during reload')
  })
})

function renderChatWorkspace(emailVerified = true) {
  const queryClient = createTestQueryClient()
  return render(() => (
    <ChatDraftProvider userId="user-id">
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <ChatWorkspace emailVerified={emailVerified} mode="page" />
        </QueryClientProvider>
      </I18nProvider>
    </ChatDraftProvider>
  ))
}

async function findReadyComposer() {
  const composer = await screen.findByRole('textbox', {
    name: /Ask about tasks/,
  })
  await waitFor(() => expect(composer).toBeEnabled())
  return composer
}

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
}

function isChatListRequest(input: RequestInfo | URL, offset = 0): boolean {
  return chatListRequestOffset(input) === offset
}

function chatListRequestOffset(input: RequestInfo | URL): number | undefined {
  const url = new URL(String(input), 'http://localhost')
  if (url.pathname !== '/api/v1/chats' || !url.searchParams.has('limit')) {
    return undefined
  }
  return Number(url.searchParams.get('offset'))
}

function createChat() {
  return {
    chat_id: 'chat-id',
    title: 'Daily work',
    is_active: true,
    created_at: '2026-07-15T09:00:00',
  }
}

function createMessage(
  chatId: string,
  role: 'assistant' | 'user',
  content: string,
  index: number,
) {
  return {
    message_id: `message-${index}`,
    chat_id: chatId,
    role,
    content,
    created_at: `2026-07-15T09:0${index}:00`,
  }
}

function agentStreamResponse(onComplete: () => void): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          'event: plan\ndata: {"objective":"Review today","status":"executable","steps":[{"step_id":"step","title":"Check today’s tasks","status":"in_progress"}]}\n\n',
        ),
      )
      setTimeout(() => {
        onComplete()
        controller.enqueue(
          encoder.encode(
            'event: result\ndata: {"status":"completed","message":"One task is due today.","data":{}}\n\n',
          ),
        )
        controller.close()
      }, 20)
    },
  })
  return new Response(stream, {
    headers: { 'Content-Type': 'text/event-stream' },
    status: 200,
  })
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}

function createMatchMedia(matches: boolean): typeof window.matchMedia {
  return vi.fn(() => ({
    addEventListener: vi.fn(),
    addListener: vi.fn(),
    dispatchEvent: vi.fn(),
    matches,
    media: '(max-width: 760px)',
    onchange: null,
    removeEventListener: vi.fn(),
    removeListener: vi.fn(),
  }))
}
