export interface Tag {
  tag_id: string
  name: string
  created_at: string
}

export interface TagListResponse {
  tags: readonly Tag[]
}
