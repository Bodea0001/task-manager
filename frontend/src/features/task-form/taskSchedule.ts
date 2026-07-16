import type { Task } from '@/entities/task/model'

type DateTimeFormatter = (
  value: Date | number,
  options: Intl.DateTimeFormatOptions,
) => string

export function formatTaskSchedule(
  task: Task,
  formatDateTime: DateTimeFormatter,
): string {
  const startsAt = task.schedule?.starts_at || task.due_at
  const endsAt = task.schedule?.ends_at || task.due_at
  const start = formatDateTime(new Date(startsAt), {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
  const end = formatDateTime(new Date(endsAt), { timeStyle: 'short' })
  return `${start} - ${end}`
}
