import { QueryClient } from '@tanstack/solid-query'
import { describe, expect, it } from 'vitest'

import {
  CALENDAR_TASKS_QUERY_KEY,
  TASKS_QUERY_KEY,
  taskQueryKey,
} from '@/entities/task/api'
import {
  addTaskToCache,
  removeTaskFromCache,
  storeTask,
} from '@/entities/task/cache'
import type { Task, TaskListResponse } from '@/entities/task/model'

describe('Task cache consistency', () => {
  it('updates known task copies without refreshing the main task list', () => {
    const queryClient = new QueryClient()
    const task = createTask()
    const calendarKey = [...CALENDAR_TASKS_QUERY_KEY, '2026-07-13'] as const
    setTaskList(queryClient, TASKS_QUERY_KEY, task)
    setTaskList(queryClient, calendarKey, task, true)
    queryClient.setQueryData(taskQueryKey(task.task_id), task)

    const updatedTask = { ...task, title: 'Updated title' }
    storeTask(queryClient, updatedTask)

    expect(taskTitles(queryClient, TASKS_QUERY_KEY)).toEqual(['Updated title'])
    expect(taskTitles(queryClient, calendarKey)).toEqual(['Updated title'])
    expect(conflictTitles(queryClient, calendarKey)).toEqual(['Updated title'])
    expect(queryClient.getQueryData(taskQueryKey(task.task_id))).toEqual(
      updatedTask,
    )
    expect(queryClient.getQueryState(TASKS_QUERY_KEY)?.isInvalidated).toBe(false)
    expect(queryClient.getQueryState(calendarKey)?.isInvalidated).toBe(true)
    expect(
      queryClient.getQueryState(taskQueryKey(task.task_id))?.isInvalidated,
    ).toBe(false)
  })

  it('marks a loaded calendar range stale when a new task may belong to it', () => {
    const queryClient = new QueryClient()
    const calendarKey = [...CALENDAR_TASKS_QUERY_KEY, '2026-07-13'] as const
    setTaskList(queryClient, TASKS_QUERY_KEY)
    setTaskList(queryClient, calendarKey)

    addTaskToCache(queryClient, createTask())

    expect(queryClient.getQueryState(TASKS_QUERY_KEY)?.isInvalidated).toBe(false)
    expect(queryClient.getQueryState(calendarKey)?.isInvalidated).toBe(true)
  })

  it('removes a deleted task from known lists without refreshing them', () => {
    const queryClient = new QueryClient()
    const task = createTask()
    const calendarKey = [...CALENDAR_TASKS_QUERY_KEY, '2026-07-13'] as const
    setTaskList(queryClient, TASKS_QUERY_KEY, task, true)
    setTaskList(queryClient, calendarKey, task, true)

    removeTaskFromCache(queryClient, task.task_id)

    expect(taskTitles(queryClient, TASKS_QUERY_KEY)).toEqual([])
    expect(conflictTitles(queryClient, TASKS_QUERY_KEY)).toEqual([])
    expect(taskTitles(queryClient, calendarKey)).toEqual([])
    expect(conflictTitles(queryClient, calendarKey)).toEqual([])
    expect(queryClient.getQueryState(TASKS_QUERY_KEY)?.isInvalidated).toBe(false)
    expect(queryClient.getQueryState(calendarKey)?.isInvalidated).toBe(false)
  })
})

function setTaskList(
  queryClient: QueryClient,
  queryKey: readonly unknown[],
  task?: Task,
  includeConflict = false,
): void {
  queryClient.setQueryData<TaskListResponse>(queryKey, {
    tasks: task === undefined ? [] : [task],
    conflicts: task !== undefined && includeConflict ? [task] : [],
  })
}

function taskTitles(
  queryClient: QueryClient,
  queryKey: readonly unknown[],
): readonly string[] {
  return (
    queryClient.getQueryData<TaskListResponse>(queryKey)?.tasks.map(
      (task) => task.title,
    ) ?? []
  )
}

function conflictTitles(
  queryClient: QueryClient,
  queryKey: readonly unknown[],
): readonly string[] {
  return (
    queryClient.getQueryData<TaskListResponse>(queryKey)?.conflicts.map(
      (task) => task.title,
    ) ?? []
  )
}

function createTask(): Task {
  return {
    task_id: 'task-id',
    title: 'Original title',
    description: null,
    status: 'active',
    priority: 'normal',
    kind: 'regular',
    due_at: '2026-07-15T13:00:00',
    created_at: '2026-07-14T10:00:00',
    completed_at: null,
    schedule: null,
    tags: [],
    recurrence_id: null,
  }
}
