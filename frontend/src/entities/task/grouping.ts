import type { Task } from '@/entities/task/model'

export type TaskView = 'today' | 'upcoming' | 'all' | 'completed'
export type TaskGroupId =
  | 'overdue'
  | 'today'
  | 'unscheduled'
  | 'upcoming'
  | 'active'
  | 'completed'
  | 'cancelled'

export interface TaskGroup {
  id: TaskGroupId
  tasks: readonly Task[]
  tone?: 'danger'
}

type ActiveTaskBucket = 'overdue' | 'today' | 'unscheduled' | 'upcoming'

export function groupTasks(
  tasks: readonly Task[],
  view: TaskView,
  now: Date,
  searchText = '',
): readonly TaskGroup[] {
  const matchingTasks = filterBySearch(tasks, searchText)

  if (view === 'today') {
    const activeTasks = matchingTasks.filter((task) => task.status === 'active')
    const buckets = bucketActiveTasks(activeTasks, now)
    return omitEmptyGroups([
      {
        id: 'overdue',
        tasks: buckets.overdue,
        tone: 'danger' as const,
      },
      { id: 'today', tasks: buckets.today },
      {
        id: 'unscheduled',
        tasks: buckets.unscheduled,
      },
    ])
  }

  if (view === 'upcoming') {
    const upcoming = matchingTasks.filter(
      (task) =>
        task.status === 'active' && getActiveTaskBucket(task, now) === 'upcoming',
    )
    return omitEmptyGroups([
      { id: 'upcoming', tasks: sortTasks(upcoming) },
    ])
  }

  if (view === 'completed') {
    return omitEmptyGroups([
      {
        id: 'completed',
        tasks: sortTasks(
          matchingTasks.filter((task) => task.status === 'completed'),
        ),
      },
    ])
  }

  return omitEmptyGroups([
    {
      id: 'active',
      tasks: sortTasks(matchingTasks.filter((task) => task.status === 'active')),
    },
    {
      id: 'completed',
      tasks: sortTasks(
        matchingTasks.filter((task) => task.status === 'completed'),
      ),
    },
    {
      id: 'cancelled',
      tasks: sortTasks(
        matchingTasks.filter((task) => task.status === 'cancelled'),
      ),
    },
  ])
}

export function countTasksForView(
  tasks: readonly Task[],
  view: TaskView,
  now: Date,
): number {
  const groups = groupTasks(tasks, view, now)

  if (view === 'today') {
    return groups.find((group) => group.id === 'today')?.tasks.length ?? 0
  }

  return groups.reduce(
    (count, group) => count + group.tasks.length,
    0,
  )
}

function bucketActiveTasks(
  tasks: readonly Task[],
  now: Date,
): Record<ActiveTaskBucket, Task[]> {
  const buckets: Record<ActiveTaskBucket, Task[]> = {
    overdue: [],
    today: [],
    unscheduled: [],
    upcoming: [],
  }

  for (const task of sortTasks(tasks)) {
    buckets[getActiveTaskBucket(task, now)].push(task)
  }

  return buckets
}

function getActiveTaskBucket(task: Task, now: Date): ActiveTaskBucket {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startOfTomorrow = new Date(startOfToday)
  startOfTomorrow.setDate(startOfTomorrow.getDate() + 1)
  const dueAt = new Date(task.due_at)
  const startsAt = task.schedule ? new Date(task.schedule.starts_at) : null

  if (dueAt < startOfToday) {
    return 'overdue'
  }

  if (
    isWithinDay(dueAt, startOfToday, startOfTomorrow) ||
    (startsAt !== null && isWithinDay(startsAt, startOfToday, startOfTomorrow))
  ) {
    return 'today'
  }

  return task.schedule === null ? 'unscheduled' : 'upcoming'
}

function isWithinDay(date: Date, start: Date, end: Date): boolean {
  return date >= start && date < end
}

function filterBySearch(
  tasks: readonly Task[],
  searchText: string,
): readonly Task[] {
  const query = searchText.trim().toLocaleLowerCase()
  if (query.length === 0) {
    return tasks
  }

  return tasks.filter((task) => {
    const searchableText = [
      task.title,
      task.description || '',
      ...task.tags.map((tag) => tag.name),
    ]
      .join(' ')
      .toLocaleLowerCase()
    return searchableText.includes(query)
  })
}

function sortTasks(tasks: readonly Task[]): Task[] {
  return [...tasks].sort((left, right) => {
    const leftTime = new Date(left.schedule?.starts_at || left.due_at).getTime()
    const rightTime = new Date(right.schedule?.starts_at || right.due_at).getTime()
    return leftTime - rightTime
  })
}

function omitEmptyGroups(groups: readonly TaskGroup[]): readonly TaskGroup[] {
  return groups.filter((group) => group.tasks.length > 0)
}
