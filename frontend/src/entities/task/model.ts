import type { Tag } from '@/entities/tag/model'

export type TaskStatus = 'active' | 'completed' | 'cancelled'
export type TaskPriority = 'low' | 'normal' | 'high' | 'urgent'
export type TaskKind = 'regular' | 'recurrence_conflict'

export interface TaskSchedule {
  starts_at: string
  ends_at: string
}

export interface Task {
  task_id: string
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  kind: TaskKind
  due_at: string
  created_at: string
  completed_at: string | null
  schedule: TaskSchedule | null
  tags: readonly Tag[]
  recurrence_id: string | null
}

export interface TaskListResponse {
  tasks: readonly Task[]
  conflicts: readonly Task[]
}
