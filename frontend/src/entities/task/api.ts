import { apiRequest } from '@/shared/api/http'
import type {
  Task,
  TaskListResponse,
  TaskPriority,
  TaskSchedule,
} from '@/entities/task/model'

export const TASKS_QUERY_KEY = ['tasks'] as const
export const CALENDAR_TASKS_QUERY_KEY = [...TASKS_QUERY_KEY, 'calendar'] as const
export const taskQueryKey = (taskId: string) =>
  [...TASKS_QUERY_KEY, taskId] as const

export interface TaskListFilters {
  due_from?: string
  due_to?: string
  starts_from?: string
  starts_to?: string
  ends_from?: string
  ends_to?: string
  limit?: number
  offset?: number
  priorities?: readonly TaskPriority[]
  statuses?: readonly Task['status'][]
}

export interface CalendarTaskFilters {
  includeDeadlines?: boolean
  includeSchedules?: boolean
  priorities?: readonly TaskPriority[]
  statuses?: readonly Task['status'][]
}

export interface UpdateTaskInput {
  title?: string
  description?: string
  priority?: TaskPriority
  due_at?: string
  schedule?: TaskSchedule
}

export interface CreateTaskInput {
  title: string
  due_at: string
  description?: string
  priority?: TaskPriority
  schedule?: TaskSchedule
  tag_ids?: readonly string[]
}

export function listTasks(filters: TaskListFilters = {}): Promise<TaskListResponse> {
  const searchParams = new URLSearchParams()
  for (const [name, value] of Object.entries(filters)) {
    if (Array.isArray(value)) {
      value.forEach((item) => searchParams.append(name, String(item)))
    } else if (value !== undefined) {
      searchParams.set(name, String(value))
    }
  }
  const query = searchParams.toString()
  return apiRequest(query.length === 0 ? '/tasks' : `/tasks?${query}`)
}

export async function listCalendarTasks(
  startsAt: string,
  endsAt: string,
  filters: CalendarTaskFilters = {},
): Promise<TaskListResponse> {
  const commonFilters = {
    priorities: filters.priorities,
    statuses: filters.statuses,
    limit: 100,
  }
  const [deadlines, schedules] = await Promise.all([
    filters.includeDeadlines === false
      ? Promise.resolve(emptyTaskList())
      : listTasks({
          ...commonFilters,
          due_from: startsAt,
          due_to: endsAt,
        }),
    filters.includeSchedules === false
      ? Promise.resolve(emptyTaskList())
      : listTasks({
          ...commonFilters,
          starts_to: endsAt,
          ends_from: startsAt,
        }),
  ])
  return {
    tasks: mergeTasks(deadlines.tasks, schedules.tasks),
    conflicts: mergeTasks(deadlines.conflicts, schedules.conflicts),
  }
}

function emptyTaskList(): TaskListResponse {
  return { tasks: [], conflicts: [] }
}

export function getTask(taskId: string): Promise<Task> {
  return apiRequest(`/tasks/${taskId}`)
}

export function createTask(data: CreateTaskInput): Promise<Task> {
  return apiRequest('/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateTask(
  taskId: string,
  data: UpdateTaskInput,
): Promise<Task> {
  return apiRequest(`/tasks/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function completeTask(taskId: string): Promise<Task> {
  return apiRequest(`/tasks/${taskId}/complete`, { method: 'POST' })
}

export function reopenTask(taskId: string): Promise<Task> {
  return apiRequest(`/tasks/${taskId}/reopen`, { method: 'POST' })
}

export function cancelTask(taskId: string): Promise<Task> {
  return apiRequest(`/tasks/${taskId}/cancel`, { method: 'POST' })
}

export function removeTaskSchedule(taskId: string): Promise<Task> {
  return apiRequest(`/tasks/${taskId}/schedule`, { method: 'DELETE' })
}

export function addTagToTask(taskId: string, tagId: string): Promise<Task> {
  return apiRequest(`/tasks/${taskId}/tags/${tagId}`, { method: 'PUT' })
}

export function removeTagFromTask(
  taskId: string,
  tagId: string,
): Promise<Task> {
  return apiRequest(`/tasks/${taskId}/tags/${tagId}`, { method: 'DELETE' })
}

export function deleteTask(taskId: string): Promise<void> {
  return apiRequest(`/tasks/${taskId}`, { method: 'DELETE' })
}

function mergeTasks(...collections: readonly (readonly Task[])[]): readonly Task[] {
  const tasks = new Map<string, Task>()
  for (const collection of collections) {
    for (const task of collection) {
      tasks.set(task.task_id, task)
    }
  }
  return [...tasks.values()]
}
