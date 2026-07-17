import { createMutation, useQueryClient } from '@tanstack/solid-query'
import ArrowLeft from 'lucide-solid/icons/arrow-left'
import Check from 'lucide-solid/icons/check'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import { createMemo, createSignal, For, Show } from 'solid-js'

import './task-creation.css'
import '@/features/task-form/task-form.css'

import {
  createTask,
  type CreateTaskInput,
} from '@/entities/task/api'
import { addTaskToCache } from '@/entities/task/cache'
import type { Task, TaskPriority } from '@/entities/task/model'
import { checkScheduleAvailability } from '@/entities/schedule/api'
import { TaskDescriptionEditor } from '@/features/task-form/TaskDescriptionEditor'
import { TaskTagField } from '@/features/task-form/TaskTagField'
import { formatTaskSchedule } from '@/features/task-form/taskSchedule'
import {
  taskPriorities,
  taskPriorityLabelKeys,
} from '@/features/task-form/taskPriorities'
import { useI18n } from '@/shared/i18n/I18nProvider'
import { ApiError } from '@/shared/api/http'
import type { TranslationKey } from '@/shared/i18n/types'
import {
  clearFormApiField,
  type FormApiError,
  toFormApiError,
} from '@/shared/forms/apiErrors'
import {
  createUnsavedChangesGuard,
  UnsavedChangesDialog,
} from '@/shared/navigation/UnsavedChangesGuard'
import { DateTimePicker } from '@/shared/ui/DateTimePicker'
import { FormErrorSummary } from '@/shared/ui/FormErrorSummary'
import { SelectField } from '@/shared/ui/SelectField'

export function TaskCreationPanel(props: {
  onCancel: () => void
  onCreated: (task: Task) => void
}) {
  const queryClient = useQueryClient()
  const { formatDateTime, t } = useI18n()
  const [title, setTitle] = createSignal('')
  const [description, setDescription] = createSignal('')
  const [priority, setPriority] = createSignal<TaskPriority>('normal')
  const [dueAt, setDueAt] = createSignal('')
  const [dueAtValid, setDueAtValid] = createSignal(false)
  const [hasSchedule, setHasSchedule] = createSignal(false)
  const [startsAt, setStartsAt] = createSignal('')
  const [startsAtValid, setStartsAtValid] = createSignal(false)
  const [endsAt, setEndsAt] = createSignal('')
  const [endsAtValid, setEndsAtValid] = createSignal(false)
  const [tagIds, setTagIds] = createSignal<readonly string[]>([])
  const [isTagOperationPending, setTagOperationPending] = createSignal(false)
  const [errorKey, setErrorKey] = createSignal<TranslationKey>()
  const [apiError, setApiError] = createSignal<FormApiError>()
  const [scheduleErrorKey, setScheduleErrorKey] = createSignal<TranslationKey>()
  const [blockingTasks, setBlockingTasks] = createSignal<readonly Task[]>([])
  const hasUnsavedChanges = createMemo(
    () =>
      title().length > 0 ||
      description().length > 0 ||
      priority() !== 'normal' ||
      dueAt().length > 0 ||
      hasSchedule() ||
      tagIds().length > 0,
  )
  // The guard reads this accessor from router and lifecycle callbacks.
  // eslint-disable-next-line solid/reactivity
  const navigationGuard = createUnsavedChangesGuard(hasUnsavedChanges)

  const creation = createMutation(() => ({
    mutationFn: (data: CreateTaskInput) => createTask(data),
    onSuccess: (task) => {
      addTaskToCache(queryClient, task)
      navigationGuard.allowNextNavigation()
      props.onCreated(task)
    },
  }))

  const clearFeedback = (field: string) => {
    setErrorKey()
    setApiError((current) => clearFormApiField(current, field))
    if (field === 'starts_at' || field === 'ends_at') {
      setScheduleErrorKey()
      setBlockingTasks([])
    }
  }

  const enableSchedule = () => {
    const initialTime = dueAt()
    setStartsAt(initialTime)
    setEndsAt(initialTime)
    setStartsAtValid(dueAtValid())
    setEndsAtValid(dueAtValid())
    setHasSchedule(true)
    setScheduleErrorKey()
    setBlockingTasks([])
  }

  const submit = async () => {
    setErrorKey()
    setApiError()
    setScheduleErrorKey()
    setBlockingTasks([])
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

    const data: CreateTaskInput = {
      title: nextTitle,
      due_at: dueAt(),
      priority: priority(),
      ...(tagIds().length > 0 ? { tag_ids: tagIds() } : {}),
      ...(nextDescription.length > 0 ? { description: nextDescription } : {}),
      ...(hasSchedule()
        ? { schedule: { starts_at: startsAt(), ends_at: endsAt() } }
        : {}),
    }
    try {
      await creation.mutateAsync(data)
    } catch (error) {
      const formError = toFormApiError(error, {
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
      if (error instanceof ApiError && error.code === 'task_schedule_overlap') {
        setScheduleErrorKey('tasks.details.errors.scheduleOverlap')
        if (hasSchedule()) {
          try {
            const availability = await checkScheduleAvailability({
              starts_at: startsAt(),
              ends_at: endsAt(),
            })
            setBlockingTasks(availability.blocking_tasks)
          } catch {
            // The conflict message remains useful when supplementary data fails.
          }
        }
        return
      }
      setErrorKey('tasks.creation.mutationError')
    }
  }

  return (
    <section class="task-creation-panel" aria-labelledby="task-creation-title">
      <header class="task-creation-header">
        <button
          type="button"
          class="task-creation-back"
          disabled={creation.isPending}
          onClick={() => {
            navigationGuard.allowNextNavigation()
            props.onCancel()
          }}
        >
          <ArrowLeft size={17} strokeWidth={2} />
          {t('tasks.creation.cancel')}
        </button>
        <h1 id="task-creation-title">{t('tasks.creation.title')}</h1>
      </header>

      <div class="task-creation-content">
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
              autofocus
              disabled={creation.isPending}
              aria-invalid={apiError()?.fieldErrors.title !== undefined}
              aria-describedby={
                apiError()?.fieldErrors.title === undefined
                  ? undefined
                  : 'task-creation-title-error'
              }
              onInput={(event) => {
                setTitle(event.currentTarget.value)
                clearFeedback('title')
              }}
            />
            <Show when={apiError()?.fieldErrors.title}>
              {(error) => (
                <small id="task-creation-title-error" class="task-field-error">
                  {error()}
                </small>
              )}
            </Show>
          </label>

          <TaskDescriptionEditor
            value={description()}
            disabled={creation.isPending}
            error={apiError()?.fieldErrors.description}
            onChange={(value) => {
              setDescription(value)
              clearFeedback('description')
            }}
          />

          <div class="task-form-fields-row">
            <SelectField
              name="priority"
              label={t('tasks.details.fields.priority')}
              value={priority()}
              disabled={creation.isPending}
              error={apiError()?.fieldErrors.priority}
              options={taskPriorities.map((option) => ({
                label: t(taskPriorityLabelKeys[option]),
                value: option,
              }))}
              onChange={(value) => {
                setPriority(value)
                clearFeedback('priority')
              }}
            />
            <DateTimePicker
              name="due_at"
              label={t('tasks.creation.deadlineLabel')}
              value={dueAt()}
              required
              disabled={creation.isPending}
              error={apiError()?.fieldErrors.due_at}
              onChange={(value) => {
                setDueAt(value)
                clearFeedback('due_at')
              }}
              onValidityChange={setDueAtValid}
            />
          </div>
          <p class="task-form-hint">
            {t(
              hasSchedule()
                ? 'tasks.creation.deadlineWithScheduleHint'
                : 'tasks.creation.deadlineHint',
            )}
          </p>

          <section
            class="task-form-section"
            aria-labelledby="task-creation-schedule-title"
          >
            <div class="task-form-section-header">
              <h3 id="task-creation-schedule-title">
                {t('tasks.details.fields.schedule')}
              </h3>
              <Show
                when={hasSchedule()}
                fallback={
                  <button
                    type="button"
                    disabled={creation.isPending}
                    onClick={enableSchedule}
                  >
                    {t('tasks.details.actions.addSchedule')}
                  </button>
                }
              >
                <button
                  type="button"
                  disabled={creation.isPending}
                  onClick={() => {
                    setHasSchedule(false)
                    setScheduleErrorKey()
                    setBlockingTasks([])
                  }}
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
                  disabled={creation.isPending}
                  error={apiError()?.fieldErrors.starts_at}
                  onChange={(value) => {
                    setStartsAt(value)
                    clearFeedback('starts_at')
                  }}
                  onValidityChange={setStartsAtValid}
                />
                <DateTimePicker
                  name="ends_at"
                  label={t('tasks.details.fields.endsAt')}
                  value={endsAt()}
                  required
                  disabled={creation.isPending}
                  error={apiError()?.fieldErrors.ends_at}
                  onChange={(value) => {
                    setEndsAt(value)
                    clearFeedback('ends_at')
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
            id="task-creation-tags"
            selectedTagIds={tagIds()}
            disabled={creation.isPending}
            onChange={(value) => {
              setTagIds(value)
              clearFeedback('tag_ids')
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

          <div class="task-creation-actions">
            <button
              type="button"
              class="secondary-button"
              disabled={creation.isPending || isTagOperationPending()}
              onClick={() => {
                navigationGuard.allowNextNavigation()
                props.onCancel()
              }}
            >
              <ArrowLeft size={16} strokeWidth={2} aria-hidden="true" />
              {t('tasks.creation.cancel')}
            </button>
            <button
              type="submit"
              class="primary-button"
              disabled={creation.isPending || isTagOperationPending()}
              aria-busy={creation.isPending}
            >
              <Show
                when={creation.isPending}
                fallback={<Check size={16} strokeWidth={2} />}
              >
                <LoaderCircle class="spin" size={16} strokeWidth={2} />
              </Show>
              {t(
                creation.isPending
                  ? 'tasks.creation.creating'
                  : 'tasks.creation.create',
              )}
            </button>
          </div>
        </form>
      </div>
      <UnsavedChangesDialog controller={navigationGuard} />
    </section>
  )
}
