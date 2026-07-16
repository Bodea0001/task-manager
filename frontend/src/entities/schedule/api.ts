import type { Task, TaskSchedule } from '@/entities/task/model'
import { apiRequest } from '@/shared/api/http'

export interface ScheduleAvailability {
  can_add_task: boolean
  blocking_tasks: readonly Task[]
}

export function checkScheduleAvailability(
  window: TaskSchedule,
): Promise<ScheduleAvailability> {
  return apiRequest('/schedules/availability', {
    method: 'POST',
    body: JSON.stringify({ window }),
  })
}
