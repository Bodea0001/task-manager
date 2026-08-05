import {
  createQuery,
  type QueryClient,
  useQueryClient,
} from '@tanstack/solid-query'
import AlertCircle from 'lucide-solid/icons/circle-alert'
import Check from 'lucide-solid/icons/check'
import CheckCircle2 from 'lucide-solid/icons/circle-check-big'
import Circle from 'lucide-solid/icons/circle'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import MessageSquareText from 'lucide-solid/icons/message-square-text'
import Pencil from 'lucide-solid/icons/pencil'
import Plus from 'lucide-solid/icons/plus'
import RotateCcw from 'lucide-solid/icons/rotate-ccw'
import SendHorizontal from 'lucide-solid/icons/send-horizontal'
import Trash2 from 'lucide-solid/icons/trash-2'
import X from 'lucide-solid/icons/x'
import {
  createEffect,
  createMemo,
  createSignal,
  For,
  Match,
  on,
  onCleanup,
  Show,
  Switch,
} from 'solid-js'

import './chat-workspace.css'

import {
  activateChat,
  CHATS_QUERY_KEY,
  chatMessagesQueryKey,
  createChat,
  deleteChat,
  listChatMessages,
  listChats,
  updateChat,
} from '@/entities/chat/api'
import type {
  AgentPlan,
  AgentPlanStep,
  AgentStreamError,
  Chat,
  ChatListResponse,
  ChatMessage,
  ChatMessageListResponse,
  PlanStepStatus,
} from '@/entities/chat/model'
import {
  AGENT_RUN_ALLOWANCE_QUERY_KEY,
  getAgentRunAllowance,
} from '@/entities/user/api'
import type { AgentRunAllowance } from '@/entities/user/model'
import { RECURRENCE_TEMPLATES_QUERY_KEY } from '@/entities/recurrence/api'
import { TAGS_QUERY_KEY } from '@/entities/tag/api'
import { invalidateTaskLists } from '@/entities/task/cache'
import {
  retryAgentStream,
  runAgentStream,
} from '@/features/chat/agentStream'
import type { AgentStreamHandlers } from '@/features/chat/agentStream'
import { useChatDrafts } from '@/features/chat/ChatDraftProvider'
import { ApiError } from '@/shared/api/http'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import { trapFocus } from '@/shared/ui/keyboard'
import { MarkdownContent } from '@/shared/ui/MarkdownContent'

const CHAT_LIST_PAGE_SIZE = 30
const MESSAGE_PAGE_SIZE = 100
const MAX_MESSAGE_LENGTH = 4_000

type WorkspaceMode = 'page' | 'panel'

type RunPreview = {
  assistant?: string
  user?: string
}

const planStatusKeys: Record<PlanStepStatus, TranslationKey> = {
  pending: 'chat.plan.pending',
  in_progress: 'chat.plan.inProgress',
  completed: 'chat.plan.completed',
  failed: 'chat.plan.failed',
}

export function ChatWorkspace(props: {
  emailVerified: boolean
  mode: WorkspaceMode
}) {
  const queryClient = useQueryClient()
  const drafts = useChatDrafts()
  const { formatDateTime, t } = useI18n()
  const [selectedChatId, setSelectedChatId] = createSignal<string>()
  const [olderMessages, setOlderMessages] = createSignal<readonly ChatMessage[]>([])
  const [nextMessageOffset, setNextMessageOffset] = createSignal<
    number | null | undefined
  >()
  const [loadingEarlier, setLoadingEarlier] = createSignal(false)
  const [loadingMoreChats, setLoadingMoreChats] = createSignal(false)
  const [loadMoreChatsError, setLoadMoreChatsError] = createSignal(false)
  const [isRunning, setRunning] = createSignal(false)
  const [plan, setPlan] = createSignal<AgentPlan>()
  const [preview, setPreview] = createSignal<RunPreview>()
  const [streamError, setStreamError] = createSignal<AgentStreamError>()
  const [retryingMessageId, setRetryingMessageId] = createSignal<string>()
  const [operationError, setOperationError] = createSignal(false)
  const [operationPending, setOperationPending] = createSignal(false)
  const [renaming, setRenaming] = createSignal(false)
  const [titleDraft, setTitleDraft] = createSignal('')
  const [confirmingDelete, setConfirmingDelete] = createSignal(false)
  const [isConversationListOpen, setConversationListOpen] = createSignal(false)
  const compactLayoutQuery =
    typeof window.matchMedia === 'function'
      ? window.matchMedia('(max-width: 760px)')
      : undefined
  const [isCompactLayout, setCompactLayout] = createSignal(
    compactLayoutQuery?.matches ?? false,
  )
  let messageList!: HTMLDivElement
  let conversationListToggle: HTMLButtonElement | undefined
  let conversationListClose: HTMLButtonElement | undefined
  let lastInitiallyScrolledChat: string | undefined

  const syncCompactLayout = (event: MediaQueryListEvent) => {
    setCompactLayout(event.matches)
    if (!event.matches) setConversationListOpen(false)
  }
  compactLayoutQuery?.addEventListener('change', syncCompactLayout)
  onCleanup(() =>
    compactLayoutQuery?.removeEventListener('change', syncCompactLayout),
  )

  const openConversationList = () => {
    setConversationListOpen(true)
    queueMicrotask(() => conversationListClose?.focus())
  }
  const closeConversationList = (restoreFocus = true) => {
    setConversationListOpen(false)
    if (restoreFocus && isCompactLayout()) {
      queueMicrotask(() => conversationListToggle?.focus())
    }
  }

  const chatsQuery = createQuery(() => ({
    queryKey: CHATS_QUERY_KEY,
    queryFn: () => listChats(CHAT_LIST_PAGE_SIZE),
  }))
  const allowanceQuery = createQuery(() => ({
    queryKey: AGENT_RUN_ALLOWANCE_QUERY_KEY,
    queryFn: getAgentRunAllowance,
  }))
  const allowance = () => allowanceQuery.data
  const isQuotaExhausted = () =>
    allowance()?.access_level === 'limited' && allowance()?.remaining === 0
  const chats = createMemo(() => chatsQuery.data?.chats || [])
  const selectedChat = createMemo(() =>
    chats().find((chat) => chat.chat_id === selectedChatId()),
  )
  const messagesQuery = createQuery(() => {
    const chat = selectedChat()
    return {
      queryKey: chatMessagesQueryKey(chat?.chat_id || 'none'),
      queryFn: () => listChatMessages(chat!.chat_id, MESSAGE_PAGE_SIZE),
      enabled: chat !== undefined,
    }
  })
  const messages = createMemo(() => {
    const chatId = selectedChatId()
    if (chatId === undefined) return []
    return [
      ...olderMessages().filter((message) => message.chat_id === chatId),
      ...(messagesQuery.data?.messages || []).filter(
        (message) => message.chat_id === chatId,
      ),
    ]
  })
  const latestMessage = createMemo(() => messages().at(-1))
  const input = () => drafts.getDraft(selectedChatId())

  createEffect(() => {
    const available = chats()
    const selected = selectedChatId()
    if (available.length === 0) {
      if (!chatsQuery.isPending) setSelectedChatId()
      return
    }
    const active = available.find((chat) => chat.is_active)
    if (active !== undefined && active.chat_id !== selected) {
      setSelectedChatId(active.chat_id)
      return
    }
    if (selected === undefined || !available.some((chat) => chat.chat_id === selected)) {
      setSelectedChatId(
        active?.chat_id || available[0].chat_id,
      )
    }
  })

  createEffect(
    on(selectedChatId, () => {
      setOlderMessages([])
      setNextMessageOffset()
      setPlan()
      setPreview()
      setStreamError()
      setRetryingMessageId()
      setOperationError(false)
      setRenaming(false)
      setConfirmingDelete(false)
    }),
  )

  createEffect(() => {
    const chatId = selectedChatId()
    const page = messagesQuery.data
    if (chatId !== undefined && page !== undefined) {
      if (nextMessageOffset() === undefined) {
        setNextMessageOffset(page.next_offset)
      }
      if (lastInitiallyScrolledChat !== chatId) {
        lastInitiallyScrolledChat = chatId
        scrollToBottom()
      }
    }
  })

  const scrollToBottom = () => {
    queueMicrotask(() => {
      if (messageList !== undefined) messageList.scrollTop = messageList.scrollHeight
    })
  }

  const addChat = async (): Promise<Chat | undefined> => {
    if (
      chatsQuery.isPending ||
      operationPending() ||
      loadingMoreChats() ||
      isRunning()
    ) {
      return undefined
    }
    setOperationPending(true)
    setOperationError(false)
    const previousChatId = selectedChatId()
    const previousDraft = drafts.getDraft(previousChatId)
    try {
      const chat = await createChat(t('chat.defaultTitle'))
      queryClient.setQueryData<ChatListResponse>(CHATS_QUERY_KEY, (current) => ({
        chats: [
          chat,
          ...(current?.chats || []).map((item) => ({
            ...item,
            is_active: false,
          })),
        ],
        next_offset:
          current?.next_offset === null || current?.next_offset === undefined
            ? null
            : current.next_offset + 1,
      }))
      queryClient.setQueryData<ChatMessageListResponse>(
        chatMessagesQueryKey(chat.chat_id),
        { messages: [], next_offset: null },
      )
      setSelectedChatId(chat.chat_id)
      closeConversationList()
      if (previousChatId === undefined && previousDraft.length > 0) {
        drafts.setDraft(chat.chat_id, previousDraft)
        drafts.clearDraft()
      }
      return chat
    } catch {
      setOperationError(true)
      return undefined
    } finally {
      setOperationPending(false)
    }
  }

  const selectChat = async (chat: Chat) => {
    if (chat.chat_id === selectedChatId()) {
      closeConversationList()
      return
    }
    if (isRunning()) return
    const previous = selectedChatId()
    const previousChats = queryClient.getQueryData<ChatListResponse>(CHATS_QUERY_KEY)
    setCachedActiveChat(queryClient, chat)
    setSelectedChatId(chat.chat_id)
    closeConversationList()
    setOperationError(false)
    try {
      const activeChat = await activateChat(chat.chat_id)
      setCachedActiveChat(queryClient, activeChat)
    } catch {
      queryClient.setQueryData(CHATS_QUERY_KEY, previousChats)
      setSelectedChatId(previous)
      setOperationError(true)
    }
  }

  const saveTitle = async () => {
    const chat = selectedChat()
    const title = titleDraft().trim()
    if (
      chat === undefined ||
      title.length === 0 ||
      operationPending() ||
      loadingMoreChats()
    ) {
      return
    }
    setOperationPending(true)
    setOperationError(false)
    try {
      const updatedChat = await updateChat(chat.chat_id, title)
      updateCachedChat(queryClient, updatedChat)
      setRenaming(false)
    } catch {
      setOperationError(true)
    } finally {
      setOperationPending(false)
    }
  }

  const removeChat = async () => {
    const chat = selectedChat()
    if (
      chat === undefined ||
      operationPending() ||
      loadingMoreChats() ||
      isRunning()
    ) {
      return
    }
    setOperationPending(true)
    setOperationError(false)
    try {
      await deleteChat(chat.chat_id)
      queryClient.setQueryData<ChatListResponse>(CHATS_QUERY_KEY, (current) => {
        if (current === undefined) return current
        return {
          ...current,
          chats: current.chats.filter((item) => item.chat_id !== chat.chat_id),
          next_offset:
            current.next_offset === null
              ? null
              : Math.max(0, current.next_offset - 1),
        }
      })
      setSelectedChatId()
      drafts.clearDraft(chat.chat_id)
      setConfirmingDelete(false)
      queueMicrotask(() => {
        queryClient.removeQueries({
          queryKey: chatMessagesQueryKey(chat.chat_id),
          exact: true,
        })
      })
    } catch {
      setOperationError(true)
    } finally {
      setOperationPending(false)
    }
  }

  const loadMoreChats = async () => {
    const offset = chatsQuery.data?.next_offset
    if (
      offset == null ||
      loadingMoreChats() ||
      operationPending() ||
      isRunning()
    ) {
      return
    }
    setLoadingMoreChats(true)
    setLoadMoreChatsError(false)
    try {
      const page = await listChats(CHAT_LIST_PAGE_SIZE, offset)
      queryClient.setQueryData<ChatListResponse>(CHATS_QUERY_KEY, (current) => ({
        chats: mergeChats(current?.chats || [], page.chats),
        next_offset: page.next_offset,
      }))
    } catch {
      setLoadMoreChatsError(true)
    } finally {
      setLoadingMoreChats(false)
    }
  }

  const loadEarlier = async () => {
    const chatId = selectedChatId()
    const offset = nextMessageOffset()
    if (chatId === undefined || offset == null || loadingEarlier()) return
    const previousHeight = messageList.scrollHeight
    setLoadingEarlier(true)
    try {
      const page = await listChatMessages(chatId, MESSAGE_PAGE_SIZE, offset)
      if (selectedChatId() !== chatId) return
      setOlderMessages((current) => [...page.messages, ...current])
      setNextMessageOffset(page.next_offset)
      queueMicrotask(() => {
        messageList.scrollTop += messageList.scrollHeight - previousHeight
      })
    } finally {
      setLoadingEarlier(false)
    }
  }

  const executeAgent = async (options: {
    chatId: string
    content: string
    draftChatId?: string
    retryMessageId?: string
  }) => {
    setRunning(true)
    setPlan()
    setStreamError()
    setRetryingMessageId(options.retryMessageId)
    setPreview(
      options.retryMessageId === undefined ? { user: options.content } : undefined,
    )
    scrollToBottom()
    let resultReceived = false
    let draftCleared = false
    const clearSubmittedDraft = () => {
      if (draftCleared || options.retryMessageId !== undefined) return
      drafts.clearDraft(options.draftChatId)
      drafts.clearDraft(options.chatId)
      draftCleared = true
    }
    try {
      const handlers: AgentStreamHandlers = {
        onPlan: (nextPlan) => {
          clearSubmittedDraft()
          setPlan(nextPlan)
          scrollToBottom()
        },
        onResult: (result) => {
          clearSubmittedDraft()
          resultReceived = true
          setPreview({
            user:
              options.retryMessageId === undefined ? options.content : undefined,
            assistant: result.message,
          })
          scrollToBottom()
        },
        onError: (error) => {
          clearSubmittedDraft()
          storeExhaustedAllowance(queryClient, error)
          setStreamError(error)
          scrollToBottom()
        },
      }
      if (options.retryMessageId === undefined) {
        await runAgentStream(options.chatId, options.content, handlers)
      } else {
        await retryAgentStream(options.chatId, handlers)
      }
      await messagesQuery.refetch()
      if (resultReceived) {
        await Promise.all([
          invalidateTaskLists(queryClient),
          queryClient.invalidateQueries({ queryKey: TAGS_QUERY_KEY }),
          queryClient.invalidateQueries({ queryKey: RECURRENCE_TEMPLATES_QUERY_KEY }),
        ])
      }
    } catch (error) {
      storeExhaustedAllowance(queryClient, error)
      setStreamError(streamErrorFromException(error))
      await messagesQuery.refetch()
    } finally {
      await allowanceQuery.refetch()
      setPreview()
      setPlan()
      setRetryingMessageId()
      setRunning(false)
      scrollToBottom()
    }
  }

  const submit = async () => {
    if (chatsQuery.isPending || allowanceQuery.isPending) return
    const content = input().trim()
    if (content.length === 0 || isRunning() || isQuotaExhausted()) return
    const draftChatId = selectedChatId()
    let chatId = draftChatId
    if (chatId === undefined) {
      chatId = (await addChat())?.chat_id
      if (chatId === undefined) return
    }
    await executeAgent({ chatId, content, draftChatId })
  }

  const retryLatestRequest = async () => {
    if (
      chatsQuery.isPending ||
      allowanceQuery.isPending ||
      operationPending() ||
      isRunning() ||
      isQuotaExhausted()
    ) {
      return
    }
    const chatId = selectedChatId()
    const message = latestMessage()
    if (chatId === undefined || message?.role !== 'user') return
    await executeAgent({
      chatId,
      content: message.content,
      retryMessageId: message.message_id,
    })
  }

  const startRenaming = () => {
    const chat = selectedChat()
    if (chat === undefined) return
    setTitleDraft(chat.title)
    setRenaming(true)
    setConfirmingDelete(false)
    setOperationError(false)
  }

  return (
    <section
      class="chat-workspace"
      classList={{
        'chat-workspace--page': props.mode === 'page',
        'chat-workspace--panel': props.mode === 'panel',
      }}
      aria-label={t('chat.label')}
    >
      <Show when={props.mode === 'page'}>
        <aside
          id="chat-conversation-list"
          class="chat-sidebar"
          classList={{ 'chat-sidebar--open': isConversationListOpen() }}
          aria-label={t('chat.conversations')}
          aria-hidden={
            isCompactLayout() && !isConversationListOpen() ? 'true' : undefined
          }
          aria-modal={
            isCompactLayout() && isConversationListOpen() ? 'true' : undefined
          }
          role={
            isCompactLayout() && isConversationListOpen() ? 'dialog' : undefined
          }
          inert={isCompactLayout() && !isConversationListOpen()}
          onKeyDown={(event) => {
            if (event.key === 'Escape') closeConversationList()
            if (isCompactLayout() && isConversationListOpen()) {
              trapFocus(event, event.currentTarget)
            }
          }}
        >
          <header>
            <h1>{t('chat.conversations')}</h1>
            <div class="chat-sidebar-actions">
              <Show when={isCompactLayout()}>
                <button
                  ref={(element) => {
                    conversationListClose = element
                  }}
                  type="button"
                  class="chat-sidebar-close"
                  aria-label={t('chat.closeConversations')}
                  title={t('chat.closeConversations')}
                  onClick={() => closeConversationList()}
                >
                  <X size={17} strokeWidth={2} />
                </button>
              </Show>
              <button
                type="button"
                disabled={
                  chatsQuery.isPending ||
                  operationPending() ||
                  loadingMoreChats() ||
                  isRunning()
                }
                aria-label={t('chat.newChat')}
                title={t('chat.newChat')}
                onClick={() => void addChat()}
              >
                <Plus size={17} strokeWidth={2} />
              </button>
            </div>
          </header>
          <Switch>
            <Match when={chatsQuery.isPending}>
              <div class="chat-list-state" aria-label={t('chat.loadingChats')}>
                <LoaderCircle class="spin" size={18} strokeWidth={1.9} />
              </div>
            </Match>
            <Match when={chatsQuery.isError}>
              <div class="chat-list-state" role="alert">
                <AlertCircle size={18} strokeWidth={1.9} />
                <span>{t('chat.loadChatsError')}</span>
                <button type="button" onClick={() => void chatsQuery.refetch()}>
                  {t('common.actions.retry')}
                </button>
              </div>
            </Match>
            <Match when={chats().length === 0}>
              <div class="chat-list-empty">
                <MessageSquareText size={20} strokeWidth={1.8} />
                <strong>{t('chat.noChats')}</strong>
                <span>{t('chat.noChatsMessage')}</span>
              </div>
            </Match>
            <Match when={chats().length > 0}>
              <div class="chat-list">
                <For each={chats()}>
                  {(chat) => (
                    <button
                      type="button"
                      class="chat-list-item"
                      classList={{
                        'chat-list-item--selected': chat.chat_id === selectedChatId(),
                      }}
                      disabled={isRunning()}
                      aria-label={t('chat.selectChat', { title: chat.title })}
                      onClick={() => void selectChat(chat)}
                    >
                      <strong>{chat.title}</strong>
                      <span>
                        {formatDateTime(new Date(chat.created_at), {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })}
                      </span>
                    </button>
                  )}
                </For>
                <Show when={chatsQuery.data?.next_offset !== null}>
                  <button
                    type="button"
                    class="chat-load-more"
                    disabled={loadingMoreChats() || operationPending() || isRunning()}
                    onClick={() => void loadMoreChats()}
                  >
                    <Show when={loadingMoreChats()}>
                      <LoaderCircle class="spin" size={14} strokeWidth={2} />
                    </Show>
                    {t(
                      loadingMoreChats()
                        ? 'chat.loadingMoreChats'
                        : 'chat.loadMoreChats',
                    )}
                  </button>
                </Show>
                <Show when={loadMoreChatsError()}>
                  <span class="chat-load-more-error" role="alert">
                    {t('chat.loadMoreChatsError')}
                  </span>
                </Show>
              </div>
            </Match>
          </Switch>
        </aside>
        <Show when={isCompactLayout()}>
          <button
            type="button"
            class="chat-sidebar-backdrop"
            aria-label={t('chat.closeConversations')}
            aria-hidden={!isConversationListOpen() ? 'true' : undefined}
            tabindex={isConversationListOpen() ? 0 : -1}
            onClick={() => closeConversationList()}
          />
        </Show>
      </Show>

      <div class="chat-conversation">
        <ConversationHeader
          chat={selectedChat()}
          mode={props.mode}
          disabled={
            chatsQuery.isPending ||
            operationPending() ||
            loadingMoreChats() ||
            isRunning()
          }
          renaming={renaming()}
          titleDraft={titleDraft()}
          conversationListOpen={isConversationListOpen()}
          showConversationListToggle={isCompactLayout()}
          onCreate={() => void addChat()}
          onConversationListToggleReady={(element) => {
            conversationListToggle = element
          }}
          onShowConversations={openConversationList}
          onDelete={() => {
            setConfirmingDelete(true)
            setRenaming(false)
            setOperationError(false)
          }}
          onRename={startRenaming}
          onTitleChange={setTitleDraft}
          onSaveTitle={() => void saveTitle()}
          onCancelRename={() => setRenaming(false)}
        />

        <Show when={confirmingDelete()}>
          <div class="chat-confirmation" role="alert">
            <div>
              <strong>{t('chat.deleteTitle')}</strong>
              <p>{t('chat.deleteMessage')}</p>
            </div>
            <div>
              <button
                type="button"
                disabled={operationPending()}
                onClick={() => setConfirmingDelete(false)}
              >
                {t('common.actions.cancel')}
              </button>
              <button
                type="button"
                class="chat-danger-button"
                disabled={operationPending() || loadingMoreChats()}
                onClick={() => void removeChat()}
              >
                {t('chat.confirmDelete')}
              </button>
            </div>
          </div>
        </Show>
        <Show when={operationError()}>
          <p class="chat-operation-error" role="alert">
            {t('chat.operationError')}
          </p>
        </Show>

        <div class="chat-message-list" ref={messageList}>
          <Switch>
            <Match when={selectedChatId() === undefined && !chatsQuery.isPending}>
              <ChatEmpty />
            </Match>
            <Match when={messagesQuery.isPending}>
              <div class="chat-message-state" aria-label={t('chat.messages.loading')}>
                <LoaderCircle class="spin" size={20} strokeWidth={1.9} />
              </div>
            </Match>
            <Match when={messagesQuery.isError}>
              <div class="chat-message-state" role="alert">
                <AlertCircle size={20} strokeWidth={1.9} />
                <p>{t('chat.messages.loadError')}</p>
                <button type="button" onClick={() => void messagesQuery.refetch()}>
                  {t('common.actions.retry')}
                </button>
              </div>
            </Match>
            <Match when={selectedChatId() !== undefined}>
              <Show when={nextMessageOffset() !== null && nextMessageOffset() !== undefined}>
                <button
                  type="button"
                  class="chat-load-earlier"
                  disabled={loadingEarlier()}
                  onClick={() => void loadEarlier()}
                >
                  <Show when={loadingEarlier()}>
                    <LoaderCircle class="spin" size={14} strokeWidth={2} />
                  </Show>
                  {t(
                    loadingEarlier()
                      ? 'chat.messages.loadingEarlier'
                      : 'chat.messages.loadEarlier',
                  )}
                </button>
              </Show>
              <Show when={messages().length === 0 && preview() === undefined}>
                <ChatEmpty />
              </Show>
              <For each={messages()}>
                {(message) => (
                  <ChatMessageView
                    message={message}
                    retryable={
                      message.role === 'user' &&
                      message.message_id === latestMessage()?.message_id
                    }
                    retrying={retryingMessageId() === message.message_id}
                    retryDisabled={
                      allowanceQuery.isPending ||
                      operationPending() ||
                      isRunning() ||
                      isQuotaExhausted()
                    }
                    onRetry={() => void retryLatestRequest()}
                  />
                )}
              </For>
              <Show keyed when={preview()}>
                {(current) => (
                  <>
                    <Show when={current.user !== undefined}>
                      <PendingMessage role="user" content={current.user!} />
                    </Show>
                    <Show when={current.assistant !== undefined}>
                      <PendingMessage role="assistant" content={current.assistant!} />
                    </Show>
                  </>
                )}
              </Show>
              <Show keyed when={plan()}>
                {(currentPlan) => <PlanProgress plan={currentPlan} />}
              </Show>
              <Show keyed when={streamError()}>
                {(error) => (
                  <StreamError
                    emailVerified={props.emailVerified}
                    error={error}
                  />
                )}
              </Show>
              <Show when={isRunning() && plan() === undefined}>
                <div class="chat-working" aria-live="polite">
                  <LoaderCircle class="spin" size={16} strokeWidth={2} />
                  <span>{t('chat.composer.running')}</span>
                </div>
              </Show>
            </Match>
          </Switch>
        </div>

        <form
          class="chat-composer"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <textarea
            name="message"
            rows={props.mode === 'panel' ? 2 : 3}
            maxLength={MAX_MESSAGE_LENGTH}
            value={input()}
            disabled={
              chatsQuery.isPending ||
              allowanceQuery.isPending ||
              isRunning() ||
              isQuotaExhausted()
            }
            aria-label={t('chat.composer.placeholder')}
            placeholder={t('chat.composer.placeholder')}
            onInput={(event) =>
              drafts.setDraft(selectedChatId(), event.currentTarget.value)
            }
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void submit()
              }
            }}
          />
          <div>
            <div class="chat-composer-notes">
              <span class="chat-composer-keyboard-hint">
                {t('chat.composer.hint')}
              </span>
              <Show keyed when={allowance()}>
                {(currentAllowance) => {
                  const exhausted =
                    currentAllowance.access_level === 'limited' &&
                    currentAllowance.remaining === 0
                  return (
                    <span
                      class="chat-composer-allowance"
                      classList={{
                        'chat-composer-allowance--exhausted': exhausted,
                      }}
                    >
                      {currentAllowance.access_level === 'unmetered'
                        ? t('chat.composer.unmetered')
                        : exhausted
                          ? t(
                              props.emailVerified
                                ? 'chat.composer.quotaExhausted'
                                : 'chat.composer.quotaExhaustedUnverified',
                            )
                          : t('chat.composer.allowance', {
                              count: currentAllowance.remaining,
                              limit: currentAllowance.limit,
                            })}
                    </span>
                  )
                }}
              </Show>
            </div>
            <button
              type="submit"
              disabled={
                chatsQuery.isPending ||
                allowanceQuery.isPending ||
                input().trim().length === 0 ||
                isRunning() ||
                operationPending() ||
                isQuotaExhausted()
              }
              aria-label={t('chat.composer.send')}
              title={t('chat.composer.send')}
            >
              <Show
                when={isRunning()}
                fallback={<SendHorizontal size={17} strokeWidth={2} />}
              >
                <LoaderCircle class="spin" size={17} strokeWidth={2} />
              </Show>
            </button>
          </div>
        </form>
      </div>
    </section>
  )
}

function ConversationHeader(props: {
  chat: Chat | undefined
  disabled: boolean
  mode: WorkspaceMode
  renaming: boolean
  titleDraft: string
  conversationListOpen: boolean
  showConversationListToggle: boolean
  onCancelRename: () => void
  onCreate: () => void
  onConversationListToggleReady: (element: HTMLButtonElement) => void
  onDelete: () => void
  onRename: () => void
  onSaveTitle: () => void
  onShowConversations: () => void
  onTitleChange: (title: string) => void
}) {
  const { t } = useI18n()
  return (
    <header class="chat-conversation-header">
      <Show
        when={props.renaming && props.chat !== undefined}
        fallback={
          <div>
            <Show when={props.mode === 'page' && props.showConversationListToggle}>
              <button
                ref={props.onConversationListToggleReady}
                type="button"
                class="chat-conversation-list-toggle"
                aria-label={t('chat.showConversations')}
                title={t('chat.showConversations')}
                aria-expanded={props.conversationListOpen}
                aria-controls="chat-conversation-list"
                onClick={() => props.onShowConversations()}
              >
                <MessageSquareText size={16} strokeWidth={1.9} />
              </button>
            </Show>
            <strong>{props.chat?.title || t('chat.defaultTitle')}</strong>
            <Show when={props.chat?.is_active}>
              <span>{t('chat.active')}</span>
            </Show>
          </div>
        }
      >
        <form
          onSubmit={(event) => {
            event.preventDefault()
            props.onSaveTitle()
          }}
        >
          <input
            name="chat_title"
            maxlength={250}
            value={props.titleDraft}
            disabled={props.disabled}
            aria-label={t('chat.rename')}
            onInput={(event) => props.onTitleChange(event.currentTarget.value)}
          />
          <button
            type="submit"
            disabled={props.disabled || props.titleDraft.trim().length === 0}
            aria-label={t('chat.saveTitle')}
            title={t('chat.saveTitle')}
          >
            <Check size={15} strokeWidth={2} />
          </button>
          <button
            type="button"
            disabled={props.disabled}
            aria-label={t('chat.cancelRename')}
            title={t('chat.cancelRename')}
            onClick={() => props.onCancelRename()}
          >
            <X size={15} strokeWidth={2} />
          </button>
        </form>
      </Show>
      <div class="chat-conversation-actions">
        <Show when={props.chat !== undefined && !props.renaming}>
          <button
            type="button"
            disabled={props.disabled}
            aria-label={t('chat.rename')}
            title={t('chat.rename')}
            onClick={() => props.onRename()}
          >
            <Pencil size={15} strokeWidth={1.9} />
          </button>
          <Show when={props.mode === 'page'}>
            <button
              type="button"
              disabled={props.disabled}
              aria-label={t('chat.delete')}
              title={t('chat.delete')}
              onClick={() => props.onDelete()}
            >
              <Trash2 size={15} strokeWidth={1.9} />
            </button>
          </Show>
        </Show>
        <Show when={props.mode === 'panel'}>
          <button
            type="button"
            disabled={props.disabled}
            aria-label={t('chat.newChat')}
            title={t('chat.newChat')}
            onClick={() => props.onCreate()}
          >
            <Plus size={16} strokeWidth={2} />
          </button>
        </Show>
      </div>
    </header>
  )
}

function ChatEmpty() {
  const { t } = useI18n()
  return (
    <div class="chat-empty">
      <MessageSquareText size={22} strokeWidth={1.7} />
      <strong>{t('chat.noChats')}</strong>
      <p>{t('chat.messages.empty')}</p>
    </div>
  )
}

function ChatMessageView(props: {
  message: ChatMessage
  onRetry: () => void
  retryable: boolean
  retryDisabled: boolean
  retrying: boolean
}) {
  const { formatDateTime, t } = useI18n()
  return (
    <article class={`chat-message chat-message--${props.message.role}`}>
      <header>
        <strong>
          {t(
            props.message.role === 'user'
              ? 'chat.messages.user'
              : 'chat.messages.assistant',
          )}
        </strong>
        <time datetime={props.message.created_at}>
          {formatDateTime(new Date(props.message.created_at), {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </time>
      </header>
      <Show
        when={props.message.role === 'assistant'}
        fallback={<p>{props.message.content}</p>}
      >
        <MarkdownContent source={props.message.content} />
      </Show>
      <Show when={props.retryable}>
        <footer class="chat-message-retry">
          <span>{t('chat.messages.unanswered')}</span>
          <button
            type="button"
            disabled={props.retryDisabled}
            aria-label={t('chat.messages.retry')}
            onClick={() => props.onRetry()}
          >
            <Show
              when={props.retrying}
              fallback={<RotateCcw size={14} strokeWidth={2} />}
            >
              <LoaderCircle class="spin" size={14} strokeWidth={2} />
            </Show>
            {t(props.retrying ? 'chat.messages.retrying' : 'chat.messages.retry')}
          </button>
        </footer>
      </Show>
    </article>
  )
}

function PendingMessage(props: { content: string; role: 'assistant' | 'user' }) {
  const { t } = useI18n()
  return (
    <article class={`chat-message chat-message--${props.role}`}>
      <header>
        <strong>
          {t(
            props.role === 'user'
              ? 'chat.messages.user'
              : 'chat.messages.assistant',
          )}
        </strong>
      </header>
      <Show when={props.role === 'assistant'} fallback={<p>{props.content}</p>}>
        <MarkdownContent source={props.content} />
      </Show>
    </article>
  )
}

function PlanProgress(props: { plan: AgentPlan }) {
  const { t } = useI18n()
  return (
    <section class="chat-plan" aria-live="polite">
      <header>
        <strong>{t('chat.plan.title')}</strong>
        <span>{props.plan.objective}</span>
      </header>
      <ol>
        <For each={props.plan.steps}>
          {(step) => (
            <li>
              <PlanStepIcon step={step} />
              <span>{step.title}</span>
              <small>{t(planStatusKeys[step.status])}</small>
            </li>
          )}
        </For>
      </ol>
    </section>
  )
}

function PlanStepIcon(props: { step: AgentPlanStep }) {
  return (
    <span class={`chat-plan-icon chat-plan-icon--${props.step.status}`} aria-hidden="true">
      <Switch>
        <Match when={props.step.status === 'completed'}>
          <CheckCircle2 size={15} strokeWidth={2} />
        </Match>
        <Match when={props.step.status === 'in_progress'}>
          <LoaderCircle class="spin" size={15} strokeWidth={2} />
        </Match>
        <Match when={props.step.status === 'failed'}>
          <AlertCircle size={15} strokeWidth={2} />
        </Match>
        <Match when={props.step.status === 'pending'}>
          <Circle size={15} strokeWidth={1.8} />
        </Match>
      </Switch>
    </span>
  )
}

function StreamError(props: {
  emailVerified: boolean
  error: AgentStreamError
}) {
  const { t } = useI18n()
  return (
    <div class="chat-stream-error" role="alert">
      <AlertCircle size={17} strokeWidth={1.9} />
      <div>
        <strong>
          {streamErrorMessage(props.error.code, props.emailVerified, t)}
        </strong>
        <Show when={props.error.request_id.length > 0}>
          <small>
            {t('chat.errors.requestId', { requestId: props.error.request_id })}
          </small>
        </Show>
      </div>
    </div>
  )
}

function streamErrorFromException(error: unknown): AgentStreamError {
  if (error instanceof ApiError) {
    return {
      code: error.code,
      context: error.context,
      message: error.message,
      request_id: error.requestId || '',
    }
  }
  return { code: 'stream_interrupted', message: '', request_id: '' }
}

function streamErrorMessage(
  code: string,
  emailVerified: boolean,
  t: (key: TranslationKey, options?: Record<string, unknown>) => string,
): string {
  if (code === 'agent_quota_exhausted') {
    return t(
      emailVerified
        ? 'chat.errors.quotaExhausted'
        : 'chat.errors.quotaExhaustedUnverified',
    )
  }
  if (code === 'agent_run_in_progress') return t('chat.errors.runInProgress')
  if (code === 'agent_request_not_retryable') {
    return t('chat.errors.notRetryable')
  }
  if (
    code === 'agent_coordination_unavailable' ||
    code === 'agent_run_lease_lost'
  ) {
    return t('chat.errors.coordination')
  }
  if (code === 'agent_execution_failed') return t('chat.errors.execution')
  return t('chat.errors.stream')
}

function storeExhaustedAllowance(
  queryClient: QueryClient,
  error: AgentStreamError | unknown,
): void {
  if (
    typeof error !== 'object' ||
    error === null ||
    !('code' in error) ||
    error.code !== 'agent_quota_exhausted' ||
    !('context' in error) ||
    typeof error.context !== 'object' ||
    error.context === null
  ) {
    return
  }
  const context = error.context as Record<string, unknown>
  if (typeof context.used !== 'number' || typeof context.limit !== 'number') return
  queryClient.setQueryData<AgentRunAllowance>(AGENT_RUN_ALLOWANCE_QUERY_KEY, {
    used: context.used,
    access_level: 'limited',
    limit: context.limit,
    remaining: 0,
  })
}

function updateCachedChat(queryClient: QueryClient, chat: Chat): void {
  queryClient.setQueryData<ChatListResponse>(CHATS_QUERY_KEY, (current) => {
    if (current === undefined) return current
    return {
      ...current,
      chats: current.chats.map((item) =>
        item.chat_id === chat.chat_id ? chat : item,
      ),
    }
  })
}

function setCachedActiveChat(queryClient: QueryClient, chat: Chat): void {
  queryClient.setQueryData<ChatListResponse>(CHATS_QUERY_KEY, (current) => {
    if (current === undefined) return current
    return {
      ...current,
      chats: current.chats.map((item) =>
        item.chat_id === chat.chat_id
          ? { ...chat, is_active: true }
          : { ...item, is_active: false },
      ),
    }
  })
}

function mergeChats(
  current: readonly Chat[],
  additional: readonly Chat[],
): readonly Chat[] {
  const chats = new Map(current.map((chat) => [chat.chat_id, chat]))
  for (const chat of additional) chats.set(chat.chat_id, chat)
  return [...chats.values()]
}
