import { describe, expect, it } from 'vitest'

import { countTasksForView, groupTasks } from '@/entities/task/grouping'
import type { Task } from '@/entities/task/model'

const now = new Date(2026, 6, 15, 12)

describe('task grouping', () => {
  it('keeps overdue, current-day, and unscheduled work in the default view', () => {
    const groups = groupTasks(
      [
        createTask('overdue', '2026-07-14T18:00:00', null),
        createTask('today', '2026-07-15T18:00:00', null),
        createTask('unscheduled', '2026-07-20T18:00:00', null),
        createTask('future-scheduled', '2026-07-20T18:00:00', {
          starts_at: '2026-07-20T17:00:00',
          ends_at: '2026-07-20T18:00:00',
        }),
      ],
      'today',
      now,
    )

    expect(groups.map((group) => [group.id, group.tasks[0]?.task_id])).toEqual([
      ['overdue', 'overdue'],
      ['today', 'today'],
      ['unscheduled', 'unscheduled'],
    ])
  })

  it('counts only current-day work in the Today view badge', () => {
    const tasks = [
      createTask('overdue', '2026-07-14T18:00:00', null),
      createTask('today', '2026-07-15T18:00:00', null),
      createTask('unscheduled', '2026-07-20T18:00:00', null),
    ]

    expect(countTasksForView(tasks, 'today', now)).toBe(1)
  })

  it('finds tasks by title, description, or tag without changing status scope', () => {
    const matchingGroups = groupTasks(
      [
        createTask('matching', '2026-07-15T18:00:00', null, {
          tags: [{ tag_id: 'tag', name: 'Finance', created_at: '2026-07-01' }],
        }),
        createTask('other', '2026-07-15T19:00:00', null),
      ],
      'today',
      now,
      'finance',
    )

    expect(matchingGroups.flatMap((group) => group.tasks)).toMatchObject([
      { task_id: 'matching' },
    ])
  })
})

function createTask(
  taskId: string,
  dueAt: string,
  schedule: Task['schedule'],
  overrides: Partial<Task> = {},
): Task {
  return {
    task_id: taskId,
    title: taskId,
    description: null,
    status: 'active',
    priority: 'normal',
    kind: 'regular',
    due_at: dueAt,
    created_at: '2026-07-01T12:00:00',
    completed_at: null,
    schedule,
    tags: [],
    recurrence_id: null,
    ...overrides,
  }
}
