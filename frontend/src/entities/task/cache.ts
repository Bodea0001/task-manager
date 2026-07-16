import type { QueryClient } from '@tanstack/solid-query'

import {
  CALENDAR_TASKS_QUERY_KEY,
  TASKS_QUERY_KEY,
  taskQueryKey,
} from '@/entities/task/api'
import type { Task, TaskListResponse } from '@/entities/task/model'

export function addTaskToCache(queryClient: QueryClient, task: Task): void {
  queryClient.setQueryData<TaskListResponse>(TASKS_QUERY_KEY, (current) => {
    if (current === undefined) {
      return { tasks: [task], conflicts: [] }
    }
    return { ...current, tasks: [task, ...current.tasks] }
  })
  queryClient.setQueryData(taskQueryKey(task.task_id), task)
  void invalidateCalendarTaskLists(queryClient)
}

export function storeTask(queryClient: QueryClient, updatedTask: Task): void {
  queryClient.setQueriesData<TaskListResponse>(taskListQueryFilter(), (current) => {
    if (current === undefined) {
      return current
    }

    return {
      ...current,
      tasks: current.tasks.map((task) =>
        task.task_id === updatedTask.task_id ? updatedTask : task,
      ),
      conflicts: current.conflicts.map((task) =>
        task.task_id === updatedTask.task_id ? updatedTask : task,
      ),
    }
  })
  queryClient.setQueryData(taskQueryKey(updatedTask.task_id), updatedTask)
  void invalidateCalendarTaskLists(queryClient)
}

export function removeTaskFromCache(
  queryClient: QueryClient,
  taskId: string,
): void {
  queryClient.setQueriesData<TaskListResponse>(taskListQueryFilter(), (current) => {
    if (current === undefined) {
      return current
    }

    return {
      ...current,
      tasks: current.tasks.filter((task) => task.task_id !== taskId),
      conflicts: current.conflicts.filter((task) => task.task_id !== taskId),
    }
  })
  queryClient.removeQueries({ queryKey: taskQueryKey(taskId), exact: true })
}

export function invalidateTaskLists(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries(taskListQueryFilter())
}

function invalidateCalendarTaskLists(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: CALENDAR_TASKS_QUERY_KEY })
}

export function removeTagFromTaskCaches(
  queryClient: QueryClient,
  tagId: string,
): void {
  queryClient.setQueriesData<TaskListResponse>(taskListQueryFilter(), (current) => {
    if (current === undefined) {
      return current
    }
    return {
      tasks: current.tasks.map((task) => removeTag(task, tagId)),
      conflicts: current.conflicts.map((task) => removeTag(task, tagId)),
    }
  })
  queryClient.setQueriesData<Task>(
    {
      predicate: (query) =>
        query.queryKey.length === 2 && query.queryKey[0] === TASKS_QUERY_KEY[0],
    },
    (task) => (task === undefined ? task : removeTag(task, tagId)),
  )
}

function removeTag(task: Task, tagId: string): Task {
  return {
    ...task,
    tags: task.tags.filter((tag) => tag.tag_id !== tagId),
  }
}

function taskListQueryFilter() {
  return {
    predicate: (query: { queryKey: readonly unknown[] }) =>
      query.queryKey.length === 1 ||
      query.queryKey[1] === CALENDAR_TASKS_QUERY_KEY[1],
    queryKey: TASKS_QUERY_KEY,
  }
}
