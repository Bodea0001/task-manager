import type { Tag } from '@/entities/tag/model'
import type {
  TaskPriority,
  TaskSchedule,
  TaskStatus,
} from '@/entities/task/model'

export type RecurrenceFrequency = 'daily' | 'weekly' | 'monthly'

export type RecurrenceBusinessDayPolicy =
  | 'none'
  | 'next_business_day'
  | 'previous_business_day'

export type Weekday = 1 | 2 | 3 | 4 | 5 | 6 | 7

export interface RecurrenceMonthRule {
  month_day: number | null
  week_of_month: -1 | 1 | 2 | 3 | 4 | 5 | null
  weekday: Weekday | null
  business_day_policy: RecurrenceBusinessDayPolicy
}

export interface RecurrenceRule {
  recurrence_id: string
  template_id: string
  frequency: RecurrenceFrequency
  interval: number
  anchor_date: string
  default_time: string
  default_duration: string | null
  weekdays: readonly Weekday[]
  month_rule: RecurrenceMonthRule | null
  schedule: TaskSchedule | null
  repeat_until: string | null
  occurrences_limit: number | null
}

export interface RecurrenceTemplate {
  template_id: string
  title: string
  description: string | null
  priority: TaskPriority
  created_at: string
  tags: readonly Tag[]
  rules: readonly RecurrenceRule[]
}

export interface RecurrenceTemplateListResponse {
  templates: readonly RecurrenceTemplate[]
}

export interface RecurrenceOccurrence {
  recurrence_id: string
  task_id: string | null
  original_starts_at: string
  due_at: string
  schedule: TaskSchedule | null
  is_cancelled: boolean
}

export interface RecurrenceOccurrenceListResponse {
  occurrences: readonly RecurrenceOccurrence[]
}

export interface UpdateRecurrenceOccurrenceInput {
  title?: string
  description?: string
  status?: TaskStatus
  priority?: TaskPriority
  due_at?: string
  schedule?: TaskSchedule
  is_cancelled?: boolean
}
