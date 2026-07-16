import type { TaskPriority } from '@/entities/task/model'
import type { TranslationKey } from '@/shared/i18n/types'

export const taskPriorities: readonly TaskPriority[] = [
  'low',
  'normal',
  'high',
  'urgent',
]

export const taskPriorityLabelKeys: Record<TaskPriority, TranslationKey> = {
  low: 'tasks.priorities.low',
  normal: 'tasks.priorities.normal',
  high: 'tasks.priorities.high',
  urgent: 'tasks.priorities.urgent',
}
