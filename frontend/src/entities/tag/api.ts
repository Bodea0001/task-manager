import { apiRequest } from '@/shared/api/http'
import type { Tag, TagListResponse } from '@/entities/tag/model'

export const TAGS_QUERY_KEY = ['tags'] as const

export function listTags(): Promise<TagListResponse> {
  return apiRequest('/tags')
}

export function createTag(name: string): Promise<Tag> {
  return apiRequest('/tags', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export function deleteTag(tagId: string): Promise<void> {
  return apiRequest(`/tags/${tagId}`, { method: 'DELETE' })
}
