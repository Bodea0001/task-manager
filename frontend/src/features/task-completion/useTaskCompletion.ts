import { createMutation, useQueryClient } from '@tanstack/solid-query'

import {
  completeTask,
  reopenTask,
} from '@/entities/task/api'
import { storeTask } from '@/entities/task/cache'
import type { Task } from '@/entities/task/model'

interface ChangeTaskStatusInput {
  taskId: string
  shouldComplete: boolean
}

export function useTaskCompletion(onTaskUpdated?: (task: Task) => void) {
  const queryClient = useQueryClient()

  return createMutation(() => ({
    mutationFn: ({ taskId, shouldComplete }: ChangeTaskStatusInput) =>
      shouldComplete ? completeTask(taskId) : reopenTask(taskId),
    onSuccess: (updatedTask: Task) => {
      storeTask(queryClient, updatedTask)
      onTaskUpdated?.(updatedTask)
    },
  }))
}
