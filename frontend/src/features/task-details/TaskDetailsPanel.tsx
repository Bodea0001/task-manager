import { createMutation, createQuery, useQueryClient } from '@tanstack/solid-query'
import AlertCircle from 'lucide-solid/icons/circle-alert'
import ArrowLeft from 'lucide-solid/icons/arrow-left'
import Check from 'lucide-solid/icons/check'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import Trash2 from 'lucide-solid/icons/trash-2'
import {
  createSignal,
  For,
  Match,
  onMount,
  Show,
  Switch,
  untrack,
} from 'solid-js'

import './task-details.css'
import '@/features/task-form/task-form.css'

import { TaskDescriptionEditor } from '@/features/task-form/TaskDescriptionEditor'
import { TaskTagField } from '@/features/task-form/TaskTagField'
import { formatTaskSchedule } from '@/features/task-form/taskSchedule'
import {
  taskPriorities,
  taskPriorityLabelKeys,
} from '@/features/task-form/taskPriorities'
import {
  addTagToTask,
  cancelTask,
  completeTask,
  deleteTask,
  getTask,
  removeTagFromTask,
  removeTaskSchedule,
  reopenTask,
  taskQueryKey,
  updateTask,
  type UpdateTaskInput,
} from '@/entities/task/api'
import {
  invalidateTaskLists,
  removeTaskFromCache,
  storeTask,
} from '@/entities/task/cache'
import type { Task } from '@/entities/task/model'
import { checkScheduleAvailability } from '@/entities/schedule/api'
import { ApiError } from '@/shared/api/http'
import {
  clearFormApiField,
  type FormApiError,
  toFormApiError,
} from '@/shared/forms/apiErrors'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import {
  createUnsavedChangesGuard,
  UnsavedChangesDialog,
} from '@/shared/navigation/UnsavedChangesGuard'
import { DateTimePicker } from '@/shared/ui/DateTimePicker'
import { FormErrorSummary } from '@/shared/ui/FormErrorSummary'
import { SelectField } from '@/shared/ui/SelectField'

const statusLabelKeys: Record<Task['status'], TranslationKey> = {
  active: 'tasks.details.status.active',
  completed: 'tasks.details.status.completed',
  cancelled: 'tasks.details.status.cancelled',
}

type StatusAction = 'cancel' | 'complete' | 'reopen'

interface TaskFormChanges {
  data: UpdateTaskInput
  removeSchedule: boolean
  tagIdsToAdd: readonly string[]
  tagIdsToRemove: readonly string[]
}

class TaskFormSaveError extends Error {
  readonly originalError: unknown
  readonly hasPartialChanges: boolean

  constructor(
    originalError: unknown,
    hasPartialChanges: boolean,
  ) {
    super('Task form changes could not be saved')
    this.originalError = originalError
    this.hasPartialChanges = hasPartialChanges
  }
}

export function TaskDetailsPanel(props: {
  backLabel?: string
  taskId: string
  onClose: () => void
}) {
  const { formatDateTime, t } = useI18n()
  let titleHeading!: HTMLHeadingElement
  const taskQuery = createQuery(() => ({
    queryKey: taskQueryKey(props.taskId),
    queryFn: () => getTask(props.taskId),
    staleTime: 30_000,
  }))
  onMount(() => queueMicrotask(() => titleHeading.focus()))

  return (
    <section
      class="task-details-panel"
      aria-labelledby="task-details-title"
    >
      <header class="task-details-header">
        <button
          type="button"
          class="task-details-back"
          onClick={() => props.onClose()}
        >
          <ArrowLeft size={17} strokeWidth={2} />
          {props.backLabel || t('tasks.details.close')}
        </button>
        <div class="task-details-heading">
          <h1 ref={titleHeading} id="task-details-title" tabIndex={-1}>
            {taskQuery.data?.title || t('tasks.details.title')}
          </h1>
          <div>
            <Show when={taskQuery.data}>
              {(task) => (
                <span class={`task-details-status task-details-status--${task().status}`}>
                  {t(statusLabelKeys[task().status])}
                </span>
              )}
            </Show>
            <Show when={taskQuery.data}>
              {(task) => (
                <span class="task-details-created">
                  {t('tasks.details.fields.createdAt', {
                    date: formatDateTime(new Date(task().created_at), {
                      dateStyle: 'medium',
                      timeStyle: 'short',
                    }),
                  })}
                </span>
              )}
            </Show>
          </div>
        </div>
      </header>

      <Switch>
        <Match when={taskQuery.isPending}>
          <div class="task-details-state" aria-label={t('tasks.details.loading')}>
            <LoaderCircle class="spin" size={24} strokeWidth={1.8} />
            <span>{t('tasks.details.loading')}</span>
          </div>
        </Match>
        <Match when={taskQuery.isError}>
          <div class="task-details-state" role="alert">
            <AlertCircle size={24} strokeWidth={1.8} />
            <h2>{t('tasks.details.loadErrorTitle')}</h2>
            <p>{t('tasks.details.loadErrorMessage')}</p>
            <button
              type="button"
              class="secondary-button"
              onClick={() => void taskQuery.refetch()}
            >
              {t('common.actions.retry')}
            </button>
          </div>
        </Match>
        <Match when={taskQuery.data !== undefined}>
          <Show keyed when={taskQuery.data}>
            {(task) => (
              <TaskDetailsForm task={task} onDeleted={() => props.onClose()} />
            )}
          </Show>
        </Match>
      </Switch>
    </section>
  )
}

function TaskDetailsForm(props: { task: Task; onDeleted: () => void }) {
  const queryClient = useQueryClient()
  const { formatDateTime, t } = useI18n()
  const initialTask = untrack(() => props.task)
  const initialTitle = initialTask.title.trim()
  const initialDescription = (initialTask.description || '').trim()
  const initialDueAt = toDateTimeInput(initialTask.due_at)
  const initialStartsAt = toDateTimeInput(
    initialTask.schedule?.starts_at || initialTask.due_at,
  )
  const initialEndsAt = toDateTimeInput(
    initialTask.schedule?.ends_at || initialTask.due_at,
  )
  const [title, setTitle] = createSignal(initialTitle)
  const [description, setDescription] = createSignal(initialDescription)
  const [priority, setPriority] = createSignal(initialTask.priority)
  const [dueAt, setDueAt] = createSignal(initialDueAt)
  const [dueAtValid, setDueAtValid] = createSignal(true)
  const [hasSchedule, setHasSchedule] = createSignal(initialTask.schedule !== null)
  const [startsAt, setStartsAt] = createSignal(initialStartsAt)
  const [startsAtValid, setStartsAtValid] = createSignal(true)
  const [endsAt, setEndsAt] = createSignal(initialEndsAt)
  const [endsAtValid, setEndsAtValid] = createSignal(true)
  const initialTagIds = initialTask.tags.map((tag) => tag.tag_id)
  const [tagIds, setTagIds] = createSignal<readonly string[]>(initialTagIds)
  const [isTagOperationPending, setTagOperationPending] = createSignal(false)
  const [errorKey, setErrorKey] = createSignal<TranslationKey>()
  const [apiError, setApiError] = createSignal<FormApiError>()
  const [scheduleErrorKey, setScheduleErrorKey] = createSignal<TranslationKey>()
  const [blockingTasks, setBlockingTasks] = createSignal<readonly Task[]>([])
  const [isDeleteConfirmationOpen, setDeleteConfirmationOpen] = createSignal(false)
  const [isDeleted, setDeleted] = createSignal(false)

  const saveMutation = createMutation(() => ({
    mutationFn: async (changes: TaskFormChanges) => {
      let task = initialTask
      let hasPersistedChanges = false
      try {
        if (Object.keys(changes.data).length > 0) {
          task = await updateTask(initialTask.task_id, changes.data)
          hasPersistedChanges = true
        }
        if (changes.removeSchedule) {
          task = await removeTaskSchedule(initialTask.task_id)
          hasPersistedChanges = true
        }
        for (const tagId of changes.tagIdsToRemove) {
          task = await removeTagFromTask(initialTask.task_id, tagId)
          hasPersistedChanges = true
        }
        for (const tagId of changes.tagIdsToAdd) {
          task = await addTagToTask(initialTask.task_id, tagId)
          hasPersistedChanges = true
        }
      } catch (error) {
        throw new TaskFormSaveError(error, hasPersistedChanges)
      }
      return task
    },
    onSuccess: (task) => storeTask(queryClient, task),
    onError: (error) => {
      if (
        error instanceof TaskFormSaveError &&
        error.hasPartialChanges
      ) {
        void invalidateTaskLists(queryClient)
      }
    },
  }))
  const statusMutation = createMutation(() => ({
    mutationFn: (action: StatusAction) => {
      if (action === 'complete') {
        return completeTask(props.task.task_id)
      }
      if (action === 'cancel') {
        return cancelTask(props.task.task_id)
      }
      return reopenTask(props.task.task_id)
    },
    onSuccess: (task) => storeTask(queryClient, task),
  }))
  const deleteMutation = createMutation(() => ({
    mutationFn: () => deleteTask(props.task.task_id),
    onSuccess: () => {
      removeTaskFromCache(queryClient, props.task.task_id)
      setDeleted(true)
      props.onDeleted()
    },
  }))
  const isPending = () =>
    saveMutation.isPending ||
    statusMutation.isPending ||
    deleteMutation.isPending ||
    isTagOperationPending()
  const hasScheduleChanges = () =>
    hasSchedule() !== (initialTask.schedule !== null) ||
    (hasSchedule() &&
      (startsAt() !== initialStartsAt || endsAt() !== initialEndsAt))
  const hasTagChanges = () =>
    tagIds().length !== initialTagIds.length ||
    tagIds().some((tagId) => !initialTagIds.includes(tagId))
  const hasFormChanges = () =>
    title().trim() !== initialTitle ||
    description().trim() !== initialDescription ||
    priority() !== initialTask.priority ||
    dueAt() !== initialDueAt ||
    hasScheduleChanges() ||
    hasTagChanges()
  const navigationGuard = createUnsavedChangesGuard(
    () => !isDeleted() && hasFormChanges(),
  )

  const clearScheduleError = () => {
    setScheduleErrorKey()
    setBlockingTasks([])
  }

  const clearFieldFeedback = (field: string) => {
    setErrorKey()
    setApiError((current) => clearFormApiField(current, field))
  }

  const runMutation = async (operation: () => Promise<unknown>) => {
    setErrorKey()
    setApiError()
    clearScheduleError()
    try {
      await operation()
      setDeleteConfirmationOpen(false)
    } catch (error) {
      const originalError =
        error instanceof TaskFormSaveError ? error.originalError : error
      const formError = toFormApiError(originalError, {
        fields: [
          'title',
          'description',
          'priority',
          'due_at',
          'starts_at',
          'ends_at',
          'tag_ids',
        ],
        aliases: {
          'schedule.starts_at': 'starts_at',
          'schedule.ends_at': 'ends_at',
        },
      })
      setApiError(formError)
      if (
        originalError instanceof ApiError &&
        originalError.code === 'task_schedule_overlap'
      ) {
        setScheduleErrorKey('tasks.details.errors.scheduleOverlap')
        if (hasSchedule()) {
          try {
            const availability = await checkScheduleAvailability({
              starts_at: startsAt(),
              ends_at: endsAt(),
            })
            setBlockingTasks(
              availability.blocking_tasks.filter(
                (task) => task.task_id !== initialTask.task_id,
              ),
            )
          } catch {
            // Conflict details are supplementary; retain the primary error.
          }
        }
        return
      }
      setErrorKey('tasks.details.mutationError')
    }
  }

  const submit = async () => {
    const nextTitle = title().trim()
    const nextDescription = description().trim()
    if (nextTitle.length === 0) {
      setErrorKey('tasks.details.validation.title')
      return
    }
    if (dueAt().length === 0) {
      setErrorKey('tasks.details.validation.dueAt')
      return
    }
    if (!dueAtValid()) {
      setErrorKey('common.validation.invalidDateTime')
      return
    }
    if (props.task.description !== null && nextDescription.length === 0) {
      setErrorKey('tasks.details.validation.description')
      return
    }
    if (hasSchedule() && (startsAt().length === 0 || endsAt().length === 0)) {
      setErrorKey('tasks.details.validation.schedule')
      return
    }
    if (hasSchedule() && (!startsAtValid() || !endsAtValid())) {
      setErrorKey('common.validation.invalidDateTime')
      return
    }
    if (hasSchedule() && endsAt() < startsAt()) {
      setErrorKey('tasks.details.validation.scheduleOrder')
      return
    }

    const data: UpdateTaskInput = {}
    if (nextTitle !== initialTitle) {
      data.title = nextTitle
    }
    if (nextDescription !== initialDescription) {
      data.description = nextDescription
    }
    if (priority() !== initialTask.priority) {
      data.priority = priority()
    }
    if (dueAt() !== initialDueAt) {
      data.due_at = dueAt()
    }
    if (hasScheduleChanges()) {
      if (hasSchedule()) {
        data.schedule = { starts_at: startsAt(), ends_at: endsAt() }
      }
    }
    const shouldRemoveSchedule =
      !hasSchedule() && initialTask.schedule !== null
    const tagIdsToAdd = tagIds().filter((tagId) => !initialTagIds.includes(tagId))
    const tagIdsToRemove = initialTagIds.filter((tagId) => !tagIds().includes(tagId))
    if (
      Object.keys(data).length === 0 &&
      !shouldRemoveSchedule &&
      tagIdsToAdd.length === 0 &&
      tagIdsToRemove.length === 0
    ) {
      return
    }
    await runMutation(() =>
      saveMutation.mutateAsync({
        data,
        removeSchedule: shouldRemoveSchedule,
        tagIdsToAdd,
        tagIdsToRemove,
      }),
    )
  }

  const stageScheduleRemoval = () => {
    setHasSchedule(false)
    clearScheduleError()
  }

  return (
    <div class="task-details-content">
      <form
        class="task-form"
        novalidate
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <label>
          <span>{t('tasks.details.fields.title')}</span>
          <input
            class="task-form-title-input"
            name="title"
            value={title()}
            maxlength={250}
            required
            disabled={isPending()}
            aria-invalid={apiError()?.fieldErrors.title !== undefined}
            aria-describedby={
              apiError()?.fieldErrors.title === undefined
                ? undefined
                : 'task-details-title-error'
            }
            onInput={(event) => {
              setTitle(event.currentTarget.value)
              clearFieldFeedback('title')
            }}
          />
          <Show when={apiError()?.fieldErrors.title}>
            {(error) => (
              <small id="task-details-title-error" class="task-field-error">
                {error()}
              </small>
            )}
          </Show>
        </label>

        <TaskDescriptionEditor
          value={description()}
          disabled={isPending()}
          error={apiError()?.fieldErrors.description}
          onChange={(value) => {
            setDescription(value)
            clearFieldFeedback('description')
          }}
        />

        <div class="task-form-fields-row">
          <SelectField
            name="priority"
            label={t('tasks.details.fields.priority')}
            value={priority()}
            disabled={isPending()}
            error={apiError()?.fieldErrors.priority}
            options={taskPriorities.map((option) => ({
              label: t(taskPriorityLabelKeys[option]),
              value: option,
            }))}
            onChange={(value) => {
              setPriority(value)
              clearFieldFeedback('priority')
            }}
          />
          <DateTimePicker
            name="due_at"
            label={t('tasks.details.fields.dueAt')}
            value={dueAt()}
            required
            disabled={isPending()}
            error={apiError()?.fieldErrors.due_at}
            onChange={(value) => {
              setDueAt(value)
              clearFieldFeedback('due_at')
            }}
            onValidityChange={setDueAtValid}
          />
        </div>

        <section class="task-form-section" aria-labelledby="task-schedule-title">
          <div class="task-form-section-header">
            <h3 id="task-schedule-title">{t('tasks.details.fields.schedule')}</h3>
            <Show
              when={hasSchedule()}
              fallback={
                <button
                  type="button"
                disabled={isPending()}
                onClick={() => {
                  setHasSchedule(true)
                  clearScheduleError()
                }}
                >
                  {t('tasks.details.actions.addSchedule')}
                </button>
              }
            >
              <button
                type="button"
                disabled={isPending()}
                onClick={stageScheduleRemoval}
              >
                {t('tasks.details.actions.removeSchedule')}
              </button>
            </Show>
          </div>
          <Show when={hasSchedule()}>
            <div class="task-form-fields-row">
              <DateTimePicker
                name="starts_at"
                label={t('tasks.details.fields.startsAt')}
                value={startsAt()}
                required
                disabled={isPending()}
                error={apiError()?.fieldErrors.starts_at}
                onChange={(value) => {
                  setStartsAt(value)
                  clearScheduleError()
                  clearFieldFeedback('starts_at')
                }}
                onValidityChange={setStartsAtValid}
              />
              <DateTimePicker
                name="ends_at"
                label={t('tasks.details.fields.endsAt')}
                value={endsAt()}
                required
                disabled={isPending()}
                error={apiError()?.fieldErrors.ends_at}
                onChange={(value) => {
                  setEndsAt(value)
                  clearScheduleError()
                  clearFieldFeedback('ends_at')
                }}
                onValidityChange={setEndsAtValid}
              />
            </div>
          </Show>
          <Show when={scheduleErrorKey()}>
            {(key) => (
              <FormErrorSummary
                error={apiError()}
                message={t(key())}
                fieldLabels={{
                  starts_at: t('tasks.details.fields.startsAt'),
                  ends_at: t('tasks.details.fields.endsAt'),
                }}
              />
            )}
          </Show>
          <Show when={blockingTasks().length > 0}>
            <div class="task-schedule-conflicts">
              <strong>{t('tasks.details.errors.conflictsTitle')}</strong>
              <ul>
                <For each={blockingTasks()}>
                  {(task) => (
                    <li>
                      <span>{task.title}</span>
                      <time>{formatTaskSchedule(task, formatDateTime)}</time>
                    </li>
                  )}
                </For>
              </ul>
            </div>
          </Show>
        </section>

        <TaskTagField
          id="task-details-tags"
          knownTags={initialTask.tags}
          selectedTagIds={tagIds()}
          disabled={isPending()}
          onChange={(value) => {
            setTagIds(value)
            clearFieldFeedback('tag_ids')
          }}
          onPendingChange={setTagOperationPending}
        />

        <Show when={errorKey()}>
          {(key) => (
            <FormErrorSummary
              error={apiError()}
              message={t(
                apiError()?.code === 'request_validation_error'
                  ? 'common.validation.summary'
                  : key(),
              )}
              fieldLabels={{
                title: t('tasks.details.fields.title'),
                description: t('tasks.details.fields.description'),
                priority: t('tasks.details.fields.priority'),
                due_at: t('tasks.details.fields.dueAt'),
                starts_at: t('tasks.details.fields.startsAt'),
                ends_at: t('tasks.details.fields.endsAt'),
                tag_ids: t('tasks.details.fields.tags'),
              }}
            />
          )}
        </Show>

        <button
          type="submit"
          class="primary-button"
          disabled={isPending() || !hasFormChanges()}
          aria-busy={saveMutation.isPending}
        >
          <Show when={saveMutation.isPending} fallback={<Check size={16} strokeWidth={2} />}>
            <LoaderCircle class="spin" size={16} strokeWidth={2} />
          </Show>
          {t(saveMutation.isPending ? 'tasks.details.actions.saving' : 'tasks.details.actions.save')}
        </button>
      </form>

      <div class="task-details-actions">
        <Show when={props.task.status === 'active'}>
          <button
            type="button"
            disabled={isPending()}
            onClick={() => void runMutation(() => statusMutation.mutateAsync('complete'))}
          >
            {t('tasks.details.actions.complete')}
          </button>
          <button
            type="button"
            disabled={isPending()}
            onClick={() => void runMutation(() => statusMutation.mutateAsync('cancel'))}
          >
            {t('tasks.details.actions.cancelTask')}
          </button>
        </Show>
        <Show when={props.task.status !== 'active'}>
          <button
            type="button"
            disabled={isPending()}
            onClick={() => void runMutation(() => statusMutation.mutateAsync('reopen'))}
          >
            {t('tasks.details.actions.reopen')}
          </button>
        </Show>
        <button
          type="button"
          class="task-details-delete-action"
          disabled={isPending()}
          onClick={() => setDeleteConfirmationOpen(true)}
        >
          <Trash2 size={15} strokeWidth={1.9} />
          {t('tasks.details.actions.deleteTask')}
        </button>
      </div>

      <Show when={isDeleteConfirmationOpen()}>
        <div class="task-details-confirmation" role="alert">
          <div>
            <strong>{t('tasks.details.confirmations.deleteTitle')}</strong>
            <p>{t('tasks.details.confirmations.deleteMessage')}</p>
          </div>
          <div>
            <button
              type="button"
              disabled={isPending()}
              onClick={() => setDeleteConfirmationOpen(false)}
            >
              {t('tasks.details.actions.cancel')}
            </button>
            <button
              type="button"
              class="task-details-confirm-danger"
              disabled={isPending()}
              onClick={() =>
                void runMutation(() => deleteMutation.mutateAsync())
              }
            >
              {t('tasks.details.actions.confirmDelete')}
            </button>
          </div>
        </div>
      </Show>
      <UnsavedChangesDialog controller={navigationGuard} />
    </div>
  )
}

function toDateTimeInput(value: string): string {
  const [date, time] = value.split('T')
  return date && time ? `${date}T${time.slice(0, 5)}` : ''
}
