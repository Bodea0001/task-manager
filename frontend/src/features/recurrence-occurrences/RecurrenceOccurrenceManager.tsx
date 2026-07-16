import { createMutation, createQuery, useQueryClient } from '@tanstack/solid-query'
import AlertCircle from 'lucide-solid/icons/circle-alert'
import AlertTriangle from 'lucide-solid/icons/triangle-alert'
import ChevronLeft from 'lucide-solid/icons/chevron-left'
import ChevronRight from 'lucide-solid/icons/chevron-right'
import Clock3 from 'lucide-solid/icons/clock-3'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import Pencil from 'lucide-solid/icons/pencil'
import RotateCcw from 'lucide-solid/icons/rotate-ccw'
import SkipForward from 'lucide-solid/icons/skip-forward'
import {
  createEffect,
  createMemo,
  createSignal,
  For,
  Match,
  Show,
  Switch,
  untrack,
} from 'solid-js'

import './recurrence-occurrence-manager.css'
import '@/features/recurrence-mutations/recurrence-mutations.css'

import {
  listRecurrenceOccurrences,
  recurrenceOccurrencesQueryKey,
  skipRecurrenceOccurrence,
  updateRecurrenceOccurrence,
} from '@/entities/recurrence/api'
import type {
  RecurrenceFrequency,
  RecurrenceOccurrence,
  RecurrenceOccurrenceListResponse,
  RecurrenceTemplate,
  UpdateRecurrenceOccurrenceInput,
} from '@/entities/recurrence/model'
import { invalidateTaskLists } from '@/entities/task/cache'
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

const WINDOW_DAYS = 28
const PAGE_SIZE = 6

const frequencyLabelKeys: Record<RecurrenceFrequency, TranslationKey> = {
  daily: 'recurring.rules.frequency.daily',
  weekly: 'recurring.rules.frequency.weekly',
  monthly: 'recurring.rules.frequency.monthly',
}

type PendingAction =
  | {
      action: 'restore'
      occurrence: RecurrenceOccurrence
    }
  | {
      action: 'skip'
      occurrence: RecurrenceOccurrence
    }

type OccurrenceMutation =
  | {
      action: 'update'
      data: UpdateRecurrenceOccurrenceInput
      occurrence: RecurrenceOccurrence
    }
  | PendingAction

export function RecurrenceOccurrenceManager(props: {
  template: RecurrenceTemplate
}) {
  const queryClient = useQueryClient()
  const { formatDateTime, t } = useI18n()
  const initialWindowStart = startOfWeek(new Date())
  const [windowStart, setWindowStart] = createSignal(initialWindowStart)
  const [editedOccurrence, setEditedOccurrence] =
    createSignal<RecurrenceOccurrence>()
  const [pendingAction, setPendingAction] = createSignal<PendingAction>()
  const [hasMutationError, setMutationError] = createSignal(false)
  const [page, setPage] = createSignal(0)
  const window = createMemo(() => {
    const start = windowStart()
    const end = addDays(start, WINDOW_DAYS)
    return {
      endsAt: localDateTime(end),
      label: t('recurring.occurrences.period', {
        end: formatDateTime(addDays(start, WINDOW_DAYS - 1), {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
        }),
        start: formatDateTime(start, {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
        }),
      }),
      startsAt: localDateTime(start),
    }
  })
  const queryKey = () =>
    recurrenceOccurrencesQueryKey(
      props.template.template_id,
      window().startsAt,
      window().endsAt,
    )
  const occurrencesQuery = createQuery(() => ({
    queryKey: queryKey(),
    queryFn: () =>
      listRecurrenceOccurrences(
        props.template.template_id,
        window().startsAt,
        window().endsAt,
      ),
  }))
  const occurrences = createMemo(
    () => occurrencesQuery.data?.occurrences || [],
  )
  const pageCount = createMemo(() =>
    Math.max(1, Math.ceil(occurrences().length / PAGE_SIZE)),
  )
  const visibleOccurrences = createMemo(() => {
    const first = page() * PAGE_SIZE
    return occurrences().slice(first, first + PAGE_SIZE)
  })
  createEffect(() => {
    if (page() >= pageCount()) setPage(pageCount() - 1)
  })
  const mutation = createMutation(() => ({
    mutationFn: (request: OccurrenceMutation) => {
      if (request.action === 'skip') {
        return skipRecurrenceOccurrence(request.occurrence)
      }
      if (request.action === 'restore') {
        return updateRecurrenceOccurrence(
          request.occurrence,
          restoreInput(request.occurrence),
        )
      }
      return updateRecurrenceOccurrence(request.occurrence, request.data)
    },
    onSuccess: (occurrence) => {
      queryClient.setQueryData<RecurrenceOccurrenceListResponse>(
        queryKey(),
        (current) =>
          current === undefined
            ? current
            : {
                occurrences: current.occurrences.map((item) =>
                  occurrenceIdentity(item) === occurrenceIdentity(occurrence)
                    ? occurrence
                    : item,
                ),
              },
      )
      void invalidateTaskLists(queryClient)
      setEditedOccurrence()
      setPendingAction()
    },
  }))

  const runMutation = async (request: OccurrenceMutation) => {
    setMutationError(false)
    try {
      await mutation.mutateAsync(request)
    } catch (error) {
      setMutationError(true)
      throw error
    }
  }

  const confirmAction = async () => {
    const action = pendingAction()
    if (action === undefined || mutation.isPending) return
    try {
      await runMutation(action)
    } catch {
      // The confirmation remains open so the user can retry.
    }
  }

  const showWindow = (start: Date) => {
    setWindowStart(start)
    setPage(0)
    setEditedOccurrence()
    setPendingAction()
    setMutationError(false)
  }

  return (
    <div class="recurrence-occurrence-manager">
      <div class="recurrence-occurrence-toolbar">
        <div>
          <button
            type="button"
            disabled={mutation.isPending}
            aria-label={t('recurring.occurrences.previousPeriod')}
            title={t('recurring.occurrences.previousPeriod')}
            onClick={() => showWindow(addDays(windowStart(), -WINDOW_DAYS))}
          >
            <ChevronLeft size={16} strokeWidth={2} />
          </button>
          <strong aria-live="polite">{window().label}</strong>
          <button
            type="button"
            disabled={mutation.isPending}
            aria-label={t('recurring.occurrences.nextPeriod')}
            title={t('recurring.occurrences.nextPeriod')}
            onClick={() => showWindow(addDays(windowStart(), WINDOW_DAYS))}
          >
            <ChevronRight size={16} strokeWidth={2} />
          </button>
        </div>
        <button
          type="button"
          disabled={mutation.isPending}
          onClick={() => showWindow(initialWindowStart)}
        >
          {t('recurring.occurrences.currentPeriod')}
        </button>
      </div>

      <p class="recurrence-occurrence-description">
        {t('recurring.occurrences.description')}
      </p>

      <Switch>
        <Match when={occurrencesQuery.isPending}>
          <div
            class="recurrence-occurrence-state"
            aria-label={t('recurring.occurrences.loading')}
          >
            <LoaderCircle class="spin" size={18} strokeWidth={1.9} />
          </div>
        </Match>
        <Match when={occurrencesQuery.isError}>
          <div class="recurrence-occurrence-state" role="alert">
            <AlertCircle size={18} strokeWidth={1.9} />
            <span>{t('recurring.occurrences.loadError')}</span>
            <button type="button" onClick={() => void occurrencesQuery.refetch()}>
              {t('recurring.states.retry')}
            </button>
          </div>
        </Match>
        <Match when={occurrences().length === 0}>
          <p class="recurrence-occurrence-empty">
            {t('recurring.occurrences.empty')}
          </p>
        </Match>
        <Match when={occurrences().length > 0}>
          <div class="recurrence-occurrence-list">
            <For each={visibleOccurrences()}>
              {(occurrence) => (
                <Show
                  keyed
                  when={selectedOccurrence(editedOccurrence(), occurrence)}
                  fallback={
                    <Show
                      keyed
                      when={selectedAction(pendingAction(), occurrence)}
                      fallback={
                        <OccurrenceRow
                          occurrence={occurrence}
                          template={props.template}
                          disabled={mutation.isPending}
                          onEdit={() => {
                            setMutationError(false)
                            setPendingAction()
                            setEditedOccurrence(occurrence)
                          }}
                          onAction={(action) => {
                            setMutationError(false)
                            setEditedOccurrence()
                            setPendingAction({ action, occurrence })
                          }}
                        />
                      }
                    >
                      {(pending) => (
                        <OccurrenceConfirmation
                          pending={pending}
                          disabled={mutation.isPending}
                          hasError={hasMutationError()}
                          onCancel={() => {
                            setPendingAction()
                            setMutationError(false)
                          }}
                          onConfirm={() => void confirmAction()}
                        />
                      )}
                    </Show>
                  }
                >
                  {(selected) => (
                    <OccurrenceEditor
                      occurrence={selected}
                      disabled={mutation.isPending}
                      onCancel={() => {
                        setEditedOccurrence()
                        setMutationError(false)
                      }}
                      onSave={(data) =>
                        runMutation({ action: 'update', data, occurrence })
                      }
                    />
                  )}
                </Show>
              )}
            </For>
          </div>
          <Show when={occurrences().length > PAGE_SIZE}>
            <OccurrencePagination
              page={page()}
              pageCount={pageCount()}
              pageSize={PAGE_SIZE}
              total={occurrences().length}
              onPageChange={setPage}
            />
          </Show>
        </Match>
      </Switch>
    </div>
  )
}

function selectedOccurrence(
  selected: RecurrenceOccurrence | undefined,
  occurrence: RecurrenceOccurrence,
): RecurrenceOccurrence | undefined {
  return selected !== undefined &&
    occurrenceIdentity(selected) === occurrenceIdentity(occurrence)
    ? selected
    : undefined
}

function selectedAction(
  selected: PendingAction | undefined,
  occurrence: RecurrenceOccurrence,
): PendingAction | undefined {
  return selected !== undefined &&
    occurrenceIdentity(selected.occurrence) === occurrenceIdentity(occurrence)
    ? selected
    : undefined
}

function OccurrencePagination(props: {
  onPageChange: (page: number) => void
  page: number
  pageCount: number
  pageSize: number
  total: number
}) {
  const { t } = useI18n()
  const first = () => props.page * props.pageSize + 1
  const last = () => Math.min(props.total, first() + props.pageSize - 1)

  return (
    <nav
      class="recurrence-occurrence-pagination"
      aria-label={t('recurring.occurrences.pagination')}
    >
      <span aria-live="polite">
        {t('recurring.occurrences.visibleRange', {
          first: first(),
          last: last(),
          total: props.total,
        })}
      </span>
      <div>
        <button
          type="button"
          disabled={props.page === 0}
          aria-label={t('recurring.occurrences.previousPage')}
          title={t('recurring.occurrences.previousPage')}
          onClick={() => props.onPageChange(props.page - 1)}
        >
          <ChevronLeft size={15} strokeWidth={2} />
        </button>
        <button
          type="button"
          disabled={props.page >= props.pageCount - 1}
          aria-label={t('recurring.occurrences.nextPage')}
          title={t('recurring.occurrences.nextPage')}
          onClick={() => props.onPageChange(props.page + 1)}
        >
          <ChevronRight size={15} strokeWidth={2} />
        </button>
      </div>
    </nav>
  )
}

function OccurrenceConfirmation(props: {
  disabled: boolean
  hasError: boolean
  onCancel: () => void
  onConfirm: () => void
  pending: PendingAction
}) {
  const { t } = useI18n()
  const isSkip = () => props.pending.action === 'skip'

  return (
    <div class="recurrence-occurrence-interaction">
      <div class="recurrence-confirmation" role="alert">
        <div>
          <strong>
            {t(
              isSkip()
                ? 'recurring.occurrences.skipTitle'
                : 'recurring.occurrences.restoreTitle',
            )}
          </strong>
          <p>
            {t(
              isSkip()
                ? 'recurring.occurrences.skipMessage'
                : 'recurring.occurrences.restoreMessage',
            )}
          </p>
        </div>
        <div>
          <button
            type="button"
            disabled={props.disabled}
            onClick={() => props.onCancel()}
          >
            {t('recurring.rules.actions.cancel')}
          </button>
          <button
            type="button"
            class="recurrence-confirm-primary"
            disabled={props.disabled}
            aria-busy={props.disabled}
            onClick={() => props.onConfirm()}
          >
            <Show when={props.disabled}>
              <LoaderCircle class="spin" size={14} strokeWidth={2} />
            </Show>
            {t(
              isSkip()
                ? 'recurring.occurrences.confirmSkip'
                : 'recurring.occurrences.confirmRestore',
            )}
          </button>
        </div>
      </div>
      <Show when={props.hasError}>
        <p class="recurrence-form-error" role="alert">
          {t('recurring.occurrences.mutationError')}
        </p>
      </Show>
    </div>
  )
}

function OccurrenceRow(props: {
  disabled: boolean
  occurrence: RecurrenceOccurrence
  onAction: (action: PendingAction['action']) => void
  onEdit: () => void
  template: RecurrenceTemplate
}) {
  const { formatDateTime, t } = useI18n()
  const rule = () =>
    props.template.rules.find(
      (item) => item.recurrence_id === props.occurrence.recurrence_id,
    )
  const relevantDate = () =>
    new Date(
      props.occurrence.schedule?.starts_at || props.occurrence.due_at,
    )
  const timing = () => {
    if (props.occurrence.schedule === null) {
      return t('recurring.occurrences.deadline', {
        time: formatDateTime(new Date(props.occurrence.due_at), {
          timeStyle: 'short',
        }),
      })
    }
    return t('recurring.occurrences.schedule', {
      end: formatDateTime(new Date(props.occurrence.schedule.ends_at), {
        timeStyle: 'short',
      }),
      start: formatDateTime(new Date(props.occurrence.schedule.starts_at), {
        timeStyle: 'short',
      }),
    })
  }
  return (
    <article
      class="recurrence-occurrence-row"
      classList={{ 'recurrence-occurrence-row--cancelled': props.occurrence.is_cancelled }}
    >
      <span class="recurrence-occurrence-icon" aria-hidden="true">
        <Clock3 size={16} strokeWidth={1.9} />
      </span>
      <div>
        <time datetime={props.occurrence.due_at}>
          {formatDateTime(relevantDate(), {
            day: 'numeric',
            month: 'short',
            weekday: 'short',
          })}
        </time>
        <strong>{timing()}</strong>
        <Show when={rule()}>
          {(item) => <span>{t(frequencyLabelKeys[item().frequency])}</span>}
        </Show>
        <Show when={props.occurrence.is_cancelled}>
          <span class="recurrence-occurrence-cancelled">
            {t('recurring.occurrences.skipped')}
          </span>
        </Show>
      </div>
      <div class="recurrence-occurrence-actions">
        <Show when={!props.occurrence.is_cancelled}>
          <button
            type="button"
            disabled={props.disabled}
            aria-label={t('recurring.occurrences.edit')}
            title={t('recurring.occurrences.edit')}
            onClick={() => props.onEdit()}
          >
            <Pencil size={14} strokeWidth={1.9} />
          </button>
        </Show>
        <button
          type="button"
          disabled={props.disabled}
          aria-label={t(
            props.occurrence.is_cancelled
              ? 'recurring.occurrences.restore'
              : 'recurring.occurrences.skip',
          )}
          title={t(
            props.occurrence.is_cancelled
              ? 'recurring.occurrences.restore'
              : 'recurring.occurrences.skip',
          )}
          onClick={() =>
            props.onAction(props.occurrence.is_cancelled ? 'restore' : 'skip')
          }
        >
          <Show
            when={props.occurrence.is_cancelled}
            fallback={<SkipForward size={14} strokeWidth={1.9} />}
          >
            <RotateCcw size={14} strokeWidth={1.9} />
          </Show>
        </button>
      </div>
    </article>
  )
}

function OccurrenceEditor(props: {
  disabled: boolean
  occurrence: RecurrenceOccurrence
  onCancel: () => void
  onSave: (data: UpdateRecurrenceOccurrenceInput) => Promise<void>
}) {
  const { t } = useI18n()
  const initialOccurrence = untrack(() => props.occurrence)
  const initialSchedule = initialOccurrence.schedule
  const initialDueAt = toDateTimeInput(initialOccurrence.due_at)
  const initialStartsAt = toDateTimeInput(
    initialSchedule?.starts_at || addMinutes(initialOccurrence.due_at, -60),
  )
  const initialEndsAt = toDateTimeInput(
    initialSchedule?.ends_at || initialOccurrence.due_at,
  )
  const [hasSchedule, setHasSchedule] = createSignal(initialSchedule !== null)
  const [dueAt, setDueAt] = createSignal(initialDueAt)
  const [dueAtValid, setDueAtValid] = createSignal(true)
  const [startsAt, setStartsAt] = createSignal(initialStartsAt)
  const [startsAtValid, setStartsAtValid] = createSignal(true)
  const [endsAt, setEndsAt] = createSignal(initialEndsAt)
  const [endsAtValid, setEndsAtValid] = createSignal(true)
  const [errorKey, setErrorKey] = createSignal<TranslationKey>()
  const [apiError, setApiError] = createSignal<FormApiError>()
  const navigationGuard = createUnsavedChangesGuard(
    () =>
      hasSchedule() !== (initialSchedule !== null) ||
      (hasSchedule()
        ? startsAt() !== initialStartsAt || endsAt() !== initialEndsAt
        : dueAt() !== initialDueAt),
  )

  const isValid = () =>
    hasSchedule()
      ? startsAtValid() &&
        endsAtValid() &&
        startsAt().length > 0 &&
        endsAt().length > 0 &&
        endsAt() >= startsAt()
      : dueAtValid() && dueAt().length > 0

  const submit = async () => {
    setErrorKey()
    setApiError()
    if (!isValid()) {
      setErrorKey('recurring.occurrences.validation')
      return
    }
    try {
      await props.onSave(
        hasSchedule()
          ? { schedule: { starts_at: startsAt(), ends_at: endsAt() } }
          : { due_at: dueAt() },
      )
    } catch (error) {
      setApiError(
        toFormApiError(error, {
          fields: ['due_at', 'starts_at', 'ends_at'],
          aliases: {
            'schedule.starts_at': 'starts_at',
            'schedule.ends_at': 'ends_at',
          },
        }),
      )
      setErrorKey(
        error instanceof ApiError && error.code === 'task_schedule_overlap'
          ? 'recurring.occurrences.overlap'
          : 'recurring.occurrences.mutationError',
      )
    }
  }

  return (
    <form
      class="recurrence-occurrence-editor"
      novalidate
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
    >
      <header>
        <h3>{t('recurring.occurrences.editorTitle')}</h3>
      </header>
      <Show
        when={hasSchedule()}
        fallback={
          <DateTimePicker
            name="occurrence_due_at"
            label={t('recurring.occurrences.dueAt')}
            value={dueAt()}
            required
            disabled={props.disabled}
            error={apiError()?.fieldErrors.due_at}
            onChange={(value) => {
              setDueAt(value)
              setErrorKey()
              setApiError((current) => clearFormApiField(current, 'due_at'))
            }}
            onValidityChange={setDueAtValid}
          />
        }
      >
        <div class="recurrence-occurrence-fields">
          <DateTimePicker
            name="occurrence_starts_at"
            label={t('recurring.occurrences.startsAt')}
            value={startsAt()}
            required
            disabled={props.disabled}
            error={apiError()?.fieldErrors.starts_at}
            onChange={(value) => {
              setStartsAt(value)
              setErrorKey()
              setApiError((current) => clearFormApiField(current, 'starts_at'))
            }}
            onValidityChange={setStartsAtValid}
          />
          <DateTimePicker
            name="occurrence_ends_at"
            label={t('recurring.occurrences.endsAt')}
            value={endsAt()}
            required
            disabled={props.disabled}
            error={apiError()?.fieldErrors.ends_at}
            onChange={(value) => {
              setEndsAt(value)
              setErrorKey()
              setApiError((current) => clearFormApiField(current, 'ends_at'))
            }}
            onValidityChange={setEndsAtValid}
          />
        </div>
      </Show>
      <Show when={initialSchedule === null}>
        <button
          type="button"
          class="recurrence-occurrence-schedule-toggle"
          disabled={props.disabled}
          onClick={() => {
            setHasSchedule(!hasSchedule())
            setErrorKey()
            setApiError()
          }}
        >
          {t(
            hasSchedule()
              ? 'recurring.occurrences.keepDeadlineOnly'
              : 'recurring.occurrences.addSchedule',
          )}
        </button>
      </Show>
      <div class="recurrence-impact-note">
        <AlertTriangle size={16} strokeWidth={1.9} aria-hidden="true" />
        <p>{t('recurring.occurrences.editImpact')}</p>
      </div>
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
              due_at: t('recurring.occurrences.dueAt'),
              starts_at: t('recurring.occurrences.startsAt'),
              ends_at: t('recurring.occurrences.endsAt'),
            }}
          />
        )}
      </Show>
      <div class="recurrence-occurrence-editor-actions">
        <button type="button" disabled={props.disabled} onClick={() => props.onCancel()}>
          {t('recurring.rules.actions.cancel')}
        </button>
        <button type="submit" class="primary-button" disabled={props.disabled}>
          <Show when={props.disabled}>
            <LoaderCircle class="spin" size={14} strokeWidth={2} />
          </Show>
          {t('recurring.occurrences.save')}
        </button>
      </div>
      <UnsavedChangesDialog controller={navigationGuard} />
    </form>
  )
}

function restoreInput(
  occurrence: RecurrenceOccurrence,
): UpdateRecurrenceOccurrenceInput {
  return occurrence.schedule === null
    ? { status: 'active', due_at: occurrence.due_at }
    : { status: 'active', schedule: occurrence.schedule }
}

function occurrenceIdentity(occurrence: RecurrenceOccurrence): string {
  return `${occurrence.recurrence_id}:${occurrence.original_starts_at}`
}

function startOfWeek(value: Date): Date {
  const date = new Date(value)
  const day = date.getDay() || 7
  date.setDate(date.getDate() - day + 1)
  date.setHours(0, 0, 0, 0)
  return date
}

function addDays(value: Date, days: number): Date {
  const date = new Date(value)
  date.setDate(date.getDate() + days)
  return date
}

function addMinutes(value: string, minutes: number): string {
  const date = new Date(value)
  date.setMinutes(date.getMinutes() + minutes)
  return localDateTime(date)
}

function localDateTime(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function toDateTimeInput(value: string): string {
  const [date, time] = value.split('T')
  return date && time ? `${date}T${time.slice(0, 5)}` : ''
}
