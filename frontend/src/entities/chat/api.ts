import type {
  Chat,
  ChatListResponse,
  ChatMessageListResponse,
} from '@/entities/chat/model'
import { apiRequest } from '@/shared/api/http'

export const CHATS_QUERY_KEY = ['chats'] as const
export const chatMessagesQueryKey = (chatId: string) =>
  [...CHATS_QUERY_KEY, chatId, 'messages'] as const

export function listChats(
  limit = 50,
  offset = 0,
): Promise<ChatListResponse> {
  return apiRequest(`/chats?limit=${limit}&offset=${offset}`)
}

export function createChat(title: string): Promise<Chat> {
  return apiRequest('/chats', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export function activateChat(chatId: string): Promise<Chat> {
  return apiRequest(`/chats/${chatId}/activate`, { method: 'POST' })
}

export function updateChat(chatId: string, title: string): Promise<Chat> {
  return apiRequest(`/chats/${chatId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
}

export function deleteChat(chatId: string): Promise<void> {
  return apiRequest(`/chats/${chatId}`, { method: 'DELETE' })
}

export function listChatMessages(
  chatId: string,
  limit = 100,
  offset = 0,
): Promise<ChatMessageListResponse> {
  return apiRequest(`/chats/${chatId}/messages?limit=${limit}&offset=${offset}`)
}
