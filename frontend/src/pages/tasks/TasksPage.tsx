import { createQuery } from '@tanstack/solid-query'
import { useSearchParams } from '@solidjs/router'
import AlertCircle from 'lucide-solid/icons/circle-alert'
import Check from 'lucide-solid/icons/check'
import Clock3 from 'lucide-solid/icons/clock-3'
import Plus from 'lucide-solid/icons/plus'
import RefreshCw from 'lucide-solid/icons/refresh-cw'
import Repeat2 from 'lucide-solid/icons/repeat-2'
import Search from 'lucide-solid/icons/search'
import X from 'lucide-solid/icons/x'
import {
  createMemo,
  createSignal,
  For,
  Match,
  onCleanup,
  Show,
  Switch,
} from 'solid-js'

import './tasks.css'

import { listTasks, TASKS_QUERY_KEY } from '@/entities/task/api'
import {
  countTasksForView,
  groupTasks,
  type TaskGroup,
  type TaskGroupId,
  type TaskView,
} from '@/entities/task/grouping'
import type { Task, TaskPriority } from '@/entities/task/model'
import { useTaskCompletion } from '@/features/task-completion/useTaskCompletion'
import { TaskCreationPanel } from '@/features/task-creation/TaskCreationPanel'
import { TaskDetailsPanel } from '@/features/task-details/TaskDetailsPanel'
import { ApiError } from '@/shared/api/http'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import { handleHorizontalTabListKeyDown } from '@/shared/ui/keyboard'

const taskViews: readonly TaskView[] = ['today', 'upcoming', 'all', 'completed']

const taskViewLabelKeys: Record<TaskView, TranslationKey> = {
  today: 'tasks.views.today',
  upcoming: 'tasks.views.upcoming',
  all: 'tasks.views.all',
  completed: 'tasks.views.completed',
}

const taskGroupLabelKeys: Record<TaskGroupId, TranslationKey> = {
  overdue: 'tasks.groups.overdue',
  today: 'tasks.groups.today',
  unscheduled: 'tasks.groups.unscheduled',
  upcoming: 'tasks.groups.upcoming',
  active: 'tasks.groups.active',
  completed: 'tasks.groups.completed',
  cancelled: 'tasks.groups.cancelled',
}

export function TasksPage() {
  const { formatDateTime, formatNumber, t } = useI18n()
  const [searchParams, setSearchParams] = useSearchParams<{
    create?: string
    task?: string
    view?: string
  }>()
  const now = new Date()
  let tasksTitle: HTMLHeadingElement | undefined
  let highlightTimeout: ReturnType<typeof setTimeout> | undefined
  const [searchText, setSearchText] = createSignal('')
  const [highlightedTaskId, setHighlightedTaskId] = createSignal<string>()
  const activeView = (): TaskView =>
    isTaskView(searchParams.view) ? searchParams.view : 'today'
  const selectedTaskId = () => searchParams.task || undefined
  const isCreating = () => searchParams.create === '1'
  const tasksQuery = createQuery(() => ({
    queryKey: TASKS_QUERY_KEY,
    queryFn: () => listTasks(),
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 401) && failureCount < 1,
  }))
  const completion = useTaskCompletion((updatedTask) => {
    setHighlightedTaskId(updatedTask.task_id)
    clearTimeout(highlightTimeout)
    highlightTimeout = setTimeout(() => setHighlightedTaskId(), 1_600)
  })
  const tasks = () => tasksQuery.data?.tasks || []
  const groups = createMemo(() =>
    groupTasks(tasks(), activeView(), now, searchText()),
  )
  const pendingTaskId = () =>
    completion.isPending ? completion.variables?.taskId : undefined

  const returnToTaskList = () => {
    setSearchParams({ create: undefined, task: undefined }, { replace: true })
    queueMicrotask(() => tasksTitle?.focus())
  }

  onCleanup(() => clearTimeout(highlightTimeout))

  return (
    <section class="tasks-page" aria-label={t('tasks.title')}>
      <Show when={selectedTaskId() === undefined && !isCreating()}>
        <header class="tasks-header">
          <div>
            <h1
              ref={(element) => {
                tasksTitle = element
              }}
              id="tasks-title"
              tabIndex={-1}
            >
              {t('tasks.title')}
            </h1>
            <p>
              {formatDateTime(now, {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              })}
            </p>
          </div>
          <button
            type="button"
            class="tasks-create-button"
            onClick={() => setSearchParams({ create: '1', task: undefined })}
          >
            <Plus size={16} strokeWidth={2.1} />
            {t('tasks.actions.add')}
          </button>
        </header>

        <div class="tasks-toolbar">
          <div
            class="task-views"
            role="tablist"
            aria-label={t('tasks.views.label')}
            onKeyDown={(event) =>
              handleHorizontalTabListKeyDown(event, event.currentTarget)
            }
          >
            <For each={taskViews}>
              {(view) => (
                <button
                  type="button"
                  role="tab"
                  class="task-view-button"
                  classList={{
                    'task-view-button--active': activeView() === view,
                  }}
                  id={`task-view-${view}`}
                  aria-controls="task-view-content"
                  aria-selected={activeView() === view}
                  tabIndex={activeView() === view ? 0 : -1}
                  onClick={() =>
                    setSearchParams({
                      view: view === 'today' ? undefined : view,
                    })
                  }
                >
                  <span>{t(taskViewLabelKeys[view])}</span>
                  <Show when={tasksQuery.data !== undefined}>
                    <span class="task-view-count">
                      {formatNumber(countTasksForView(tasks(), view, now))}
                    </span>
                  </Show>
                </button>
              )}
            </For>
          </div>

          <div class="task-search">
            <Search size={17} strokeWidth={1.9} aria-hidden="true" />
            <label class="visually-hidden" for="task-search-input">
              {t('tasks.search.label')}
            </label>
            <input
              id="task-search-input"
              type="search"
              value={searchText()}
              placeholder={t('tasks.search.placeholder')}
              onInput={(event) => setSearchText(event.currentTarget.value)}
            />
            <Show when={searchText().length > 0}>
              <button
                type="button"
                aria-label={t('tasks.search.clear')}
                title={t('tasks.search.clear')}
                onClick={() => setSearchText('')}
              >
                <X size={15} strokeWidth={1.9} />
              </button>
            </Show>
          </div>
        </div>

        <div
          id="task-view-content"
          role="tabpanel"
          aria-labelledby={`task-view-${activeView()}`}
        >
          <Show when={completion.isError}>
            <div class="task-mutation-error" role="alert">
              <AlertCircle size={17} strokeWidth={1.9} aria-hidden="true" />
              <span>{t('tasks.states.mutationError')}</span>
              <button
                type="button"
                onClick={() => {
                  completion.reset()
                  void tasksQuery.refetch()
                }}
              >
                {t('common.actions.refreshTasks')}
              </button>
            </div>
          </Show>

          <Switch>
            <Match when={tasksQuery.isPending}>
              <TaskListSkeleton />
            </Match>
            <Match when={tasksQuery.isError}>
              <TasksErrorState
                error={tasksQuery.error}
                onRetry={() => void tasksQuery.refetch()}
              />
            </Match>
            <Match when={groups().length === 0}>
              <TasksEmptyState hasSearch={searchText().trim().length > 0} />
            </Match>
            <Match when={groups().length > 0}>
              <div class="task-groups">
                <For each={groups()}>
                  {(group) => (
                    <TaskGroupSection
                      group={group}
                      pendingTaskId={pendingTaskId()}
                      highlightedTaskId={highlightedTaskId()}
                      onToggle={(task) =>
                        completion.mutate({
                          taskId: task.task_id,
                          shouldComplete: task.status !== 'completed',
                        })
                      }
                      onOpen={(task) =>
                        setSearchParams({
                          create: undefined,
                          task: task.task_id,
                        })
                      }
                    />
                  )}
                </For>
              </div>
            </Match>
          </Switch>
        </div>
      </Show>

      <Show when={isCreating()}>
        <TaskCreationPanel
          onCancel={returnToTaskList}
          onCreated={(task) =>
            setSearchParams(
              { create: undefined, task: task.task_id },
              { replace: true },
            )
          }
        />
      </Show>

      <Show when={selectedTaskId()}>
        {(taskId) => (
          <TaskDetailsPanel taskId={taskId()} onClose={returnToTaskList} />
        )}
      </Show>
    </section>
  )
}

function isTaskView(value: string | undefined): value is TaskView {
  return value !== undefined && taskViews.includes(value as TaskView)
}

function TaskGroupSection(props: {
  group: TaskGroup
  pendingTaskId?: string
  highlightedTaskId?: string
  onToggle: (task: Task) => void
  onOpen: (task: Task) => void
}) {
  const { formatNumber, t } = useI18n()
  const taskCount = () => props.group.tasks.length

  return (
    <section class="task-group" aria-labelledby={`task-group-${props.group.id}`}>
      <header class="task-group-header">
        <h2
          id={`task-group-${props.group.id}`}
          classList={{ 'task-group-title--danger': props.group.tone === 'danger' }}
        >
          {t(taskGroupLabelKeys[props.group.id])}
        </h2>
        <span aria-label={t('tasks.itemCount', { count: taskCount() })}>
          {formatNumber(taskCount())}
        </span>
      </header>
      <div class="task-list">
        <For each={props.group.tasks}>
          {(task) => (
            <TaskRow
              task={task}
              isPending={props.pendingTaskId === task.task_id}
              isHighlighted={props.highlightedTaskId === task.task_id}
              onToggle={() => props.onToggle(task)}
              onOpen={() => props.onOpen(task)}
            />
          )}
        </For>
      </div>
    </section>
  )
}

function TaskRow(props: {
  task: Task
  isPending: boolean
  isHighlighted: boolean
  onToggle: () => void
  onOpen: () => void
}) {
  const { formatDateTime, formatNumber, t } = useI18n()
  const isCompleted = () => props.task.status === 'completed'
  const taskActionLabel = () =>
    t(isCompleted() ? 'tasks.actions.reopen' : 'tasks.actions.complete', {
      title: props.task.title,
    })
  const taskActionTitle = () =>
    t(
      isCompleted()
        ? 'tasks.actions.reopenTitle'
        : 'tasks.actions.completeTitle',
    )
  const formattedTaskTime = () => {
    const dueAt = new Date(props.task.due_at)
    const date = formatDateTime(dueAt, { day: 'numeric', month: 'short' })
    const start = formatDateTime(
      props.task.schedule ? new Date(props.task.schedule.starts_at) : dueAt,
      { hour: '2-digit', minute: '2-digit' },
    )

    if (props.task.schedule === null) {
      return t('tasks.metadata.due', { date, time: start })
    }

    const end = formatDateTime(new Date(props.task.schedule.ends_at), {
      hour: '2-digit',
      minute: '2-digit',
    })
    return t('tasks.metadata.scheduled', { date, start, end })
  }

  return (
    <article
      class="task-row"
      classList={{
        'task-row--completed': isCompleted(),
        'task-row--highlighted': props.isHighlighted,
      }}
    >
      <button
        type="button"
        class="task-status-button"
        classList={{ 'task-status-button--completed': isCompleted() }}
        aria-label={taskActionLabel()}
        title={taskActionTitle()}
        disabled={props.isPending || props.task.status === 'cancelled'}
        onClick={() => props.onToggle()}
      >
        <Show when={props.isPending} fallback={<Show when={isCompleted()}><Check size={14} strokeWidth={2.5} /></Show>}>
          <RefreshCw class="spin" size={13} strokeWidth={2} />
        </Show>
      </button>

      <button
        type="button"
        class="task-row-content task-row-open"
        aria-label={t('tasks.actions.openDetails', { title: props.task.title })}
        onClick={() => props.onOpen()}
      >
        <div class="task-row-title-line">
          <h3>{props.task.title}</h3>
          <PriorityLabel priority={props.task.priority} />
        </div>
        <div class="task-metadata">
          <span class="task-time" classList={{ 'task-time--overdue': isOverdue(props.task) }}>
            <Clock3 size={14} strokeWidth={1.9} aria-hidden="true" />
            {formattedTaskTime()}
          </span>
          <Show when={props.task.recurrence_id !== null}>
            <span>
              <Repeat2 size={14} strokeWidth={1.9} aria-hidden="true" />
              {t('tasks.metadata.recurring')}
            </span>
          </Show>
          <For each={props.task.tags.slice(0, 2)}>
            {(tag) => <span class="task-tag">{tag.name}</span>}
          </For>
          <Show when={props.task.tags.length > 2}>
            <span class="task-tag">
              +{formatNumber(props.task.tags.length - 2)}
            </span>
          </Show>
        </div>
      </button>

    </article>
  )
}

function PriorityLabel(props: { priority: TaskPriority }) {
  const { t } = useI18n()
  const priorityLabelKeys: Record<Exclude<TaskPriority, 'normal'>, TranslationKey> = {
    low: 'tasks.priorities.low',
    high: 'tasks.priorities.high',
    urgent: 'tasks.priorities.urgent',
  }

  return (
    <Show when={props.priority !== 'normal'}>
      <span class={`task-priority task-priority--${props.priority}`}>
        {t(priorityLabelKeys[props.priority as Exclude<TaskPriority, 'normal'>])}
      </span>
    </Show>
  )
}

function TasksErrorState(props: {
  error: Error | null
  onRetry: () => void
}) {
  const { t } = useI18n()
  const requiresAuthentication = () =>
    props.error instanceof ApiError && props.error.status === 401

  return (
    <div class="tasks-state" role="alert">
      <span class="tasks-state-icon tasks-state-icon--error" aria-hidden="true">
        <AlertCircle size={22} strokeWidth={1.8} />
      </span>
      <h2>
        {requiresAuthentication()
          ? t('tasks.states.signInTitle')
          : t('tasks.states.loadErrorTitle')}
      </h2>
      <p>
        {requiresAuthentication()
          ? t('tasks.states.signInMessage')
          : t('tasks.states.loadErrorMessage')}
      </p>
      <Show when={!requiresAuthentication()}>
        <button
          type="button"
          class="secondary-button"
          onClick={() => props.onRetry()}
        >
          {t('common.actions.retry')}
        </button>
      </Show>
    </div>
  )
}

function TasksEmptyState(props: { hasSearch: boolean }) {
  const { t } = useI18n()
  return (
    <div class="tasks-state">
      <span class="tasks-state-icon" aria-hidden="true">
        <Check size={22} strokeWidth={2} />
      </span>
      <h2>
        {props.hasSearch
          ? t('tasks.states.noMatchesTitle')
          : t('tasks.states.emptyTitle')}
      </h2>
      <p>
        {props.hasSearch
          ? t('tasks.states.noMatchesMessage')
          : t('tasks.states.emptyMessage')}
      </p>
    </div>
  )
}

function TaskListSkeleton() {
  const { t } = useI18n()
  return (
    <div class="task-skeleton" aria-label={t('tasks.states.loading')}>
      <For each={[0, 1, 2, 3, 4]}>
        {() => (
          <div class="task-skeleton-row">
            <span />
            <div><span /><span /></div>
          </div>
        )}
      </For>
    </div>
  )
}

function isOverdue(task: Task): boolean {
  return task.status === 'active' && new Date(task.due_at) < new Date()
}
