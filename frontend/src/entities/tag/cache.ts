import type { QueryClient } from '@tanstack/solid-query'

import { TAGS_QUERY_KEY } from '@/entities/tag/api'
import type { Tag, TagListResponse } from '@/entities/tag/model'

export function addTagToCache(queryClient: QueryClient, tag: Tag): void {
  queryClient.setQueryData<TagListResponse>(TAGS_QUERY_KEY, (current) => {
    if (current === undefined) {
      return { tags: [tag] }
    }
    return { tags: [...current.tags, tag] }
  })
}

export function removeTagFromCache(
  queryClient: QueryClient,
  tagId: string,
): void {
  queryClient.setQueryData<TagListResponse>(TAGS_QUERY_KEY, (current) => {
    if (current === undefined) {
      return current
    }
    return { tags: current.tags.filter((tag) => tag.tag_id !== tagId) }
  })
}
