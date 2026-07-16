import {
  createContext,
  createSignal,
  onCleanup,
  type ParentProps,
  untrack,
  useContext,
} from 'solid-js'

import { subscribeToAuthSession } from '@/shared/auth/session'

const CHAT_DRAFT_STORAGE_PREFIX = 'task-manager.chat-drafts'

interface ChatDraftContextValue {
  clearDraft: (chatId?: string) => void
  getDraft: (chatId?: string) => string
  setDraft: (chatId: string | undefined, value: string) => void
}

interface ChatDraftProviderProps extends ParentProps {
  userId: string
}

const ChatDraftContext = createContext<ChatDraftContextValue>()

/** Keeps per-conversation drafts available across navigation and page reloads. */
export function ChatDraftProvider(props: ChatDraftProviderProps) {
  const userId = untrack(() => props.userId)
  const [drafts, setDrafts] = createSignal<ReadonlyMap<string | undefined, string>>(
    readStoredDrafts(userId),
  )

  const getDraft = (chatId?: string) => drafts().get(chatId) || ''

  const setDraft = (chatId: string | undefined, value: string) => {
    setDrafts((current) => {
      const next = new Map(current)
      if (value.length === 0) next.delete(chatId)
      else next.set(chatId, value)
      persistDrafts(userId, next)
      return next
    })
  }

  const clearDraft = (chatId?: string) => setDraft(chatId, '')
  const unsubscribe = subscribeToAuthSession((event) => {
    if (event !== 'cleared') return
    setDrafts(new Map())
    removeStoredDrafts(userId)
  })

  onCleanup(unsubscribe)

  return (
    <ChatDraftContext.Provider value={{ clearDraft, getDraft, setDraft }}>
      {props.children}
    </ChatDraftContext.Provider>
  )
}

export function useChatDrafts(): ChatDraftContextValue {
  const context = useContext(ChatDraftContext)
  if (context === undefined) {
    throw new Error('useChatDrafts must be used within ChatDraftProvider')
  }
  return context
}

function readStoredDrafts(
  userId: string,
): ReadonlyMap<string | undefined, string> {
  try {
    const value = sessionStorage.getItem(storageKey(userId))
    if (value === null) return new Map()

    const parsed = JSON.parse(value) as unknown
    if (!Array.isArray(parsed)) return new Map()

    const drafts = new Map<string | undefined, string>()
    for (const entry of parsed) {
      if (
        !Array.isArray(entry) ||
        entry.length !== 2 ||
        (entry[0] !== null && typeof entry[0] !== 'string') ||
        typeof entry[1] !== 'string'
      ) {
        return new Map()
      }
      drafts.set(entry[0] ?? undefined, entry[1])
    }
    return drafts
  } catch {
    return new Map()
  }
}

function persistDrafts(
  userId: string,
  drafts: ReadonlyMap<string | undefined, string>,
): void {
  try {
    if (drafts.size === 0) {
      removeStoredDrafts(userId)
      return
    }
    sessionStorage.setItem(storageKey(userId), JSON.stringify([...drafts]))
  } catch {
    // Drafts remain available in memory when browser storage is unavailable.
  }
}

function removeStoredDrafts(userId: string): void {
  try {
    sessionStorage.removeItem(storageKey(userId))
  } catch {
    // In-memory cleanup is still sufficient for the current page.
  }
}

function storageKey(userId: string): string {
  return `${CHAT_DRAFT_STORAGE_PREFIX}.${userId}`
}
