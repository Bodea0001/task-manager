import { createQuery, useQueryClient } from '@tanstack/solid-query'
import { useSearchParams } from '@solidjs/router'
import AlertCircle from 'lucide-solid/icons/circle-alert'
import ChevronLeft from 'lucide-solid/icons/chevron-left'
import ChevronRight from 'lucide-solid/icons/chevron-right'
import Clock3 from 'lucide-solid/icons/clock-3'
import Flag from 'lucide-solid/icons/flag'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import RotateCcw from 'lucide-solid/icons/rotate-ccw'
import {
  createEffect,
  createMemo,
  createSignal,
  For,
  Match,
  on,
  Show,
  Switch,
} from 'solid-js'

import './calendar.css'

import {
  CALENDAR_TASKS_QUERY_KEY,
  listCalendarTasks,
  taskQueryKey,
} from '@/entities/task/api'
import type { Task, TaskPriority, TaskStatus } from '@/entities/task/model'
import {
  buildCalendarEntries,
  buildCalendarWeek,
  calendarWeekKey,
  layoutCalendarEntries,
  localDateKey,
  resolveCalendarWeek,
  resolveCalendarTimeRange,
  shiftCalendarWeek,
  type CalendarDay,
  type CalendarEntry,
} from '@/features/calendar/calendar'
import { TaskDetailsPanel } from '@/features/task-details/TaskDetailsPanel'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import { SelectField, type SelectOption } from '@/shared/ui/SelectField'
import { handleHorizontalTabListKeyDown } from '@/shared/ui/keyboard'

type CalendarKindFilter = 'all' | CalendarEntry['kind']
type CalendarPriorityFilter = 'all' | TaskPriority
type CalendarStatusFilter = 'all' | TaskStatus

const HOUR_HEIGHT = 44
const priorityLabelKeys: Record<TaskPriority, TranslationKey> = {
  low: 'tasks.priorities.low',
  normal: 'tasks.priorities.normal',
  high: 'tasks.priorities.high',
  urgent: 'tasks.priorities.urgent',
}

export function CalendarPage() {
  const queryClient = useQueryClient()
  const { formatDateTime, t } = useI18n()
  const [searchParams, setSearchParams] = useSearchParams<{
    task?: string
    week?: string
  }>()
  const [kindFilter, setKindFilter] = createSignal<CalendarKindFilter>('all')
  const [priorityFilter, setPriorityFilter] =
    createSignal<CalendarPriorityFilter>('all')
  const [statusFilter, setStatusFilter] =
    createSignal<CalendarStatusFilter>('all')
  const [todaySelectionRequest, setTodaySelectionRequest] = createSignal(0)
  const today = new Date()
  let calendarTitle: HTMLHeadingElement | undefined
  const weekStartsOn = () => resolveCalendarWeek(searchParams.week, today)
  const calendar = createMemo(() => buildCalendarWeek(weekStartsOn()))
  const tasksQuery = createQuery(() => ({
    queryKey: [
      ...CALENDAR_TASKS_QUERY_KEY,
      calendar().startsAt,
      calendar().endsAt,
      kindFilter(),
      priorityFilter(),
      statusFilter(),
    ],
    queryFn: () => {
      const priority = priorityFilter()
      const status = statusFilter()
      return listCalendarTasks(calendar().startsAt, calendar().endsAt, {
        includeDeadlines: kindFilter() !== 'schedule',
        includeSchedules: kindFilter() !== 'deadline',
        priorities: priority === 'all' ? undefined : [priority],
        statuses: status === 'all' ? undefined : [status],
      })
    },
    placeholderData: (previousData) => previousData,
  }))
  const entries = createMemo(() =>
    buildCalendarEntries(
      [
        ...(tasksQuery.data?.tasks || []),
        ...(tasksQuery.data?.conflicts || []),
      ],
      calendar(),
    ),
  )
  const filteredEntries = createMemo(() => {
    const result = new Map<string, readonly CalendarEntry[]>()
    for (const [day, dayEntries] of entries()) {
      result.set(
        day,
        dayEntries.filter(
          (entry) =>
            (kindFilter() === 'all' || entry.kind === kindFilter()) &&
            (priorityFilter() === 'all' ||
              entry.task.priority === priorityFilter()) &&
            (statusFilter() === 'all' ||
              entry.task.status === statusFilter()),
        ),
      )
    }
    return result
  })
  const filteredEntryCount = createMemo(() =>
    [...filteredEntries().values()].reduce(
      (total, day) => total + day.length,
      0,
    ),
  )
  const hasActiveFilters = () =>
    kindFilter() !== 'all' ||
    priorityFilter() !== 'all' ||
    statusFilter() !== 'all'
  const periodLabel = () => {
    const firstDay = calendar().days[0].date
    const lastDay = calendar().days.at(-1)!.date
    return t('calendar.period', {
      end: formatDateTime(lastDay, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      }),
      start: formatDateTime(firstDay, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      }),
    })
  }
  const selectedTaskId = () => searchParams.task || undefined

  const selectWeek = (nextWeek: Date) => {
    const currentWeekKey = calendarWeekKey(resolveCalendarWeek(undefined, today))
    const nextWeekKey = calendarWeekKey(nextWeek)
    setSearchParams({
      task: undefined,
      week: nextWeekKey === currentWeekKey ? undefined : nextWeekKey,
    })
  }

  const selectToday = () => {
    selectWeek(today)
    setTodaySelectionRequest((request) => request + 1)
  }

  const openTask = (task: Task) => {
    queryClient.setQueryData(taskQueryKey(task.task_id), task)
    setSearchParams({ task: task.task_id })
  }

  const closeTask = () => {
    setSearchParams({ task: undefined })
    queueMicrotask(() => calendarTitle?.focus())
  }

  return (
    <section class="calendar-page" aria-label={t('calendar.title')}>
      <Show when={selectedTaskId() === undefined}>
        <header class="calendar-header">
          <div>
            <h1
              ref={(element) => {
                calendarTitle = element
              }}
              tabIndex={-1}
            >
              {t('calendar.title')}
            </h1>
            <p>{t('calendar.description')}</p>
          </div>
          <div class="calendar-navigation">
            <button
              type="button"
              class="calendar-icon-button"
              aria-label={t('calendar.actions.previousWeek')}
              title={t('calendar.actions.previousWeek')}
              onClick={() => selectWeek(shiftCalendarWeek(weekStartsOn(), -1))}
            >
              <ChevronLeft size={18} strokeWidth={2} />
            </button>
            <strong aria-live="polite">{periodLabel()}</strong>
            <button
              type="button"
              class="calendar-icon-button"
              aria-label={t('calendar.actions.nextWeek')}
              title={t('calendar.actions.nextWeek')}
              onClick={() => selectWeek(shiftCalendarWeek(weekStartsOn(), 1))}
            >
              <ChevronRight size={18} strokeWidth={2} />
            </button>
            <button
              type="button"
              class="calendar-today-button"
              onClick={selectToday}
            >
              {t('calendar.actions.today')}
            </button>
          </div>
        </header>

        <CalendarFilters
          kind={kindFilter()}
          priority={priorityFilter()}
          status={statusFilter()}
          onKindChange={setKindFilter}
          onPriorityChange={setPriorityFilter}
          onStatusChange={setStatusFilter}
          onReset={() => {
            setKindFilter('all')
            setPriorityFilter('all')
            setStatusFilter('all')
          }}
          showReset={hasActiveFilters()}
        />

        <Switch>
          <Match when={tasksQuery.isPending}>
            <CalendarLoadingState />
          </Match>
          <Match when={tasksQuery.isError}>
            <div class="calendar-state" role="alert">
              <AlertCircle size={24} strokeWidth={1.8} />
              <h2>{t('calendar.states.errorTitle')}</h2>
              <p>{t('calendar.states.errorMessage')}</p>
              <button type="button" onClick={() => void tasksQuery.refetch()}>
                {t('calendar.actions.retry')}
              </button>
            </div>
          </Match>
          <Match when={tasksQuery.data !== undefined}>
            <Show
              when={filteredEntryCount() > 0}
              fallback={
                <p class="calendar-empty-notice">
                  {t(
                    hasActiveFilters()
                      ? 'calendar.states.noMatches'
                      : 'calendar.states.empty',
                  )}
                </p>
              }
            >
              <span class="visually-hidden" aria-live="polite">
                {periodLabel()}
              </span>
            </Show>
            <CalendarWeekGrid
              days={calendar().days}
              entries={filteredEntries()}
              periodLabel={periodLabel()}
              today={today}
              todaySelectionRequest={todaySelectionRequest()}
              onOpenTask={openTask}
            />
          </Match>
        </Switch>
      </Show>

      <Show when={selectedTaskId()}>
        {(taskId) => (
          <TaskDetailsPanel
            taskId={taskId()}
            backLabel={t('calendar.actions.back')}
            onClose={closeTask}
          />
        )}
      </Show>
    </section>
  )
}

function CalendarFilters(props: {
  kind: CalendarKindFilter
  onKindChange: (value: CalendarKindFilter) => void
  onPriorityChange: (value: CalendarPriorityFilter) => void
  onReset: () => void
  onStatusChange: (value: CalendarStatusFilter) => void
  priority: CalendarPriorityFilter
  showReset: boolean
  status: CalendarStatusFilter
}) {
  const { t } = useI18n()
  const kindOptions: SelectOption<CalendarKindFilter>[] = [
    { value: 'all', label: t('calendar.filters.allKinds') },
    { value: 'schedule', label: t('calendar.filters.scheduled') },
    { value: 'deadline', label: t('calendar.filters.deadlines') },
  ]
  const priorityOptions: SelectOption<CalendarPriorityFilter>[] = [
    { value: 'all', label: t('calendar.filters.allPriorities') },
    ...(['low', 'normal', 'high', 'urgent'] as const).map((value) => ({
      value,
      label: t(priorityLabelKeys[value]),
    })),
  ]
  const statusOptions: SelectOption<CalendarStatusFilter>[] = [
    { value: 'all', label: t('calendar.filters.allStatuses') },
    { value: 'active', label: t('tasks.details.status.active') },
    { value: 'completed', label: t('tasks.details.status.completed') },
    { value: 'cancelled', label: t('tasks.details.status.cancelled') },
  ]

  return (
    <div
      class="calendar-filters"
      role="group"
      aria-label={t('calendar.filters.label')}
    >
      <SelectField
        label={t('calendar.filters.kind')}
        value={props.kind}
        options={kindOptions}
        onChange={props.onKindChange}
      />
      <SelectField
        label={t('calendar.filters.priority')}
        value={props.priority}
        options={priorityOptions}
        onChange={props.onPriorityChange}
      />
      <SelectField
        label={t('calendar.filters.status')}
        value={props.status}
        options={statusOptions}
        onChange={props.onStatusChange}
      />
      <Show when={props.showReset}>
        <button type="button" onClick={() => props.onReset()}>
          <RotateCcw size={14} strokeWidth={2} aria-hidden="true" />
          {t('calendar.filters.reset')}
        </button>
      </Show>
    </div>
  )
}

function CalendarWeekGrid(props: {
  days: readonly CalendarDay[]
  entries: ReadonlyMap<string, readonly CalendarEntry[]>
  periodLabel: string
  today: Date
  todaySelectionRequest: number
  onOpenTask: (task: Task) => void
}) {
  const { formatDateTime, t } = useI18n()
  let timelineScroll!: HTMLDivElement
  let scrolledWeek = ''
  const defaultDayKey = () => {
    const todayKey = localDateKey(props.today)
    return props.days.some((day) => day.key === todayKey)
      ? todayKey
      : props.days[0].key
  }
  const [selectedDayKey, setSelectedDayKey] = createSignal(defaultDayKey())
  createEffect(
    on(
      () => props.todaySelectionRequest,
      () => {
        const todayKey = localDateKey(props.today)
        if (props.days.some((day) => day.key === todayKey)) {
          setSelectedDayKey(todayKey)
        }
      },
    ),
  )
  createEffect(() => {
    const days = props.days
    if (!days.some((day) => day.key === selectedDayKey())) {
      setSelectedDayKey(defaultDayKey())
    }
  })
  const selectedDay = () =>
    props.days.find((day) => day.key === selectedDayKey()) ?? props.days[0]
  const selectedEntries = () => props.entries.get(selectedDay().key) || []
  const timeRange = createMemo(() =>
    resolveCalendarTimeRange([...props.entries.values()].flat()),
  )
  const visibleHours = createMemo(() => {
    const range = timeRange()
    return Array.from(
      { length: (range.endMinute - range.startMinute) / 60 },
      (_, index) => range.startMinute / 60 + index,
    )
  })
  const timelineHeight = () =>
    ((timeRange().endMinute - timeRange().startMinute) / 60) * HOUR_HEIGHT
  createEffect(() => {
    const weekKey = props.days[0].key
    if (scrolledWeek === weekKey) return
    const firstEntryMinute = Math.min(
      ...[...props.entries.values()].flatMap((day) =>
        day.map((entry) => entry.startMinute),
      ),
    )
    const todayIsVisible = props.days.some(
      (day) => day.key === localDateKey(props.today),
    )
    const currentMinute = props.today.getHours() * 60 + props.today.getMinutes()
    const focusMinute = todayIsVisible
      ? currentMinute
      : Number.isFinite(firstEntryMinute)
        ? firstEntryMinute
        : timeRange().startMinute
    const rangeStartMinute = timeRange().startMinute
    scrolledWeek = weekKey
    queueMicrotask(() => {
      timelineScroll.scrollTop = Math.max(
        0,
        ((focusMinute - rangeStartMinute - 60) / 60) * HOUR_HEIGHT,
      )
    })
  })

  return (
    <div class="calendar-board">
      <div
        ref={timelineScroll}
        class="calendar-timeline-scroll"
        role="grid"
        aria-label={t('calendar.gridLabel', { period: props.periodLabel })}
      >
        <div class="calendar-timeline">
          <div class="calendar-timeline-header" role="row">
            <span aria-hidden="true" />
            <For each={props.days}>
              {(day) => (
                <CalendarDayHeading day={day} today={props.today} />
              )}
            </For>
          </div>
          <div
            class="calendar-timeline-body"
            style={{ height: `${timelineHeight()}px` }}
          >
            <div class="calendar-time-axis" aria-hidden="true">
              <For each={visibleHours()}>
                {(hour) => (
                  <time
                    style={{
                      top: `${((hour * 60 - timeRange().startMinute) / 60) * HOUR_HEIGHT}px`,
                    }}
                  >
                    {formatDateTime(new Date(2000, 0, 1, hour), {
                      hour: '2-digit',
                    })}
                  </time>
                )}
              </For>
            </div>
            <For each={props.days}>
              {(day) => {
                const dayEntries = () => props.entries.get(day.key) || []
                return (
                  <div
                    class="calendar-day-track"
                    classList={{
                      'calendar-day-track--today':
                        day.key === localDateKey(props.today),
                    }}
                    role="gridcell"
                    aria-label={t('calendar.dayLabel', {
                      count: dayEntries().length,
                      date: formatDateTime(day.date, { dateStyle: 'long' }),
                    })}
                  >
                    <For each={layoutCalendarEntries(dayEntries())}>
                      {(positioned) => (
                        <CalendarEntryButton
                          entry={positioned.entry}
                          dateLabel={formatDateTime(day.date, {
                            dateStyle: 'long',
                          })}
                          position={positioned}
                          rangeStartMinute={timeRange().startMinute}
                          onOpen={() =>
                            props.onOpenTask(positioned.entry.task)
                          }
                        />
                      )}
                    </For>
                    <Show
                      when={
                        day.key === localDateKey(props.today) &&
                        props.today.getHours() * 60 + props.today.getMinutes() <
                          timeRange().endMinute &&
                        props.today.getHours() * 60 + props.today.getMinutes() >=
                          timeRange().startMinute
                      }
                    >
                      <span
                        class="calendar-now-line"
                        style={{
                          top: `${((props.today.getHours() * 60 + props.today.getMinutes() - timeRange().startMinute) / 60) * HOUR_HEIGHT}px`,
                        }}
                        aria-hidden="true"
                      />
                    </Show>
                  </div>
                )
              }}
            </For>
          </div>
        </div>
      </div>

      <div class="calendar-mobile-week">
        <div
          class="calendar-mobile-days"
          role="tablist"
          onKeyDown={(event) =>
            handleHorizontalTabListKeyDown(event, event.currentTarget)
          }
        >
          <For each={props.days}>
            {(day) => (
              <button
                type="button"
                role="tab"
                id={`calendar-day-tab-${day.key}`}
                aria-controls="calendar-mobile-day-content"
                aria-label={t('calendar.mobileDayLabel', {
                  count: (props.entries.get(day.key) || []).length,
                  date: formatDateTime(day.date, { dateStyle: 'long' }),
                })}
                aria-selected={selectedDayKey() === day.key}
                tabIndex={selectedDayKey() === day.key ? 0 : -1}
                classList={{
                  'calendar-mobile-day--selected': selectedDayKey() === day.key,
                  'calendar-mobile-day--today':
                    day.key === localDateKey(props.today),
                }}
                onClick={() => setSelectedDayKey(day.key)}
              >
                <span>{formatDateTime(day.date, { weekday: 'narrow' })}</span>
                <strong>{day.date.getDate()}</strong>
                <small>{(props.entries.get(day.key) || []).length}</small>
              </button>
            )}
          </For>
        </div>
        <section
          id="calendar-mobile-day-content"
          class="calendar-mobile-day-content"
          role="tabpanel"
          aria-labelledby={`calendar-day-tab-${selectedDay().key}`}
        >
          <header>
            <h2>
              {formatDateTime(selectedDay().date, {
                day: 'numeric',
                month: 'long',
                weekday: 'long',
              })}
            </h2>
            <span>
              {t('calendar.dayTaskCount', {
                count: selectedEntries().length,
              })}
            </span>
          </header>
          <div>
            <For each={selectedEntries()}>
              {(entry) => (
                <CalendarEntryButton
                  entry={entry}
                  dateLabel={formatDateTime(selectedDay().date, {
                    dateStyle: 'long',
                  })}
                  onOpen={() => props.onOpenTask(entry.task)}
                />
              )}
            </For>
            <Show when={selectedEntries().length === 0}>
              <span class="calendar-day-empty">
                {t('calendar.states.noTasksForDay')}
              </span>
            </Show>
          </div>
        </section>
      </div>
    </div>
  )
}

function CalendarDayHeading(props: { day: CalendarDay; today: Date }) {
  const { formatDateTime } = useI18n()
  return (
    <div
      class="calendar-day-heading"
      classList={{
        'calendar-day-heading--today':
          props.day.key === localDateKey(props.today),
      }}
      role="columnheader"
    >
      <span>{formatDateTime(props.day.date, { weekday: 'short' })}</span>
      <time datetime={props.day.key}>{props.day.date.getDate()}</time>
    </div>
  )
}

function CalendarEntryButton(props: {
  dateLabel: string
  entry: CalendarEntry
  onOpen: () => void
  position?: ReturnType<typeof layoutCalendarEntries>[number]
  rangeStartMinute?: number
}) {
  const { formatDateTime, t } = useI18n()
  const task = () => props.entry.task
  const priorityLabel = () => t(priorityLabelKeys[task().priority])
  const time = () => {
    if (props.entry.kind === 'deadline') {
      return t('calendar.entries.deadline', {
        time: formatDateTime(new Date(task().due_at), {
          hour: '2-digit',
          minute: '2-digit',
        }),
      })
    }
    const schedule = task().schedule!
    const start = formatDateTime(new Date(schedule.starts_at), {
      hour: '2-digit',
      minute: '2-digit',
    })
    const end = formatDateTime(new Date(schedule.ends_at), {
      hour: '2-digit',
      minute: '2-digit',
    })
    if (props.entry.scheduleSegment === 'start') {
      return t('calendar.entries.scheduleStart', { start })
    }
    if (props.entry.scheduleSegment === 'middle') {
      return t('calendar.entries.scheduleMiddle')
    }
    if (props.entry.scheduleSegment === 'end') {
      return t('calendar.entries.scheduleEnd', { end })
    }
    return t('calendar.entries.schedule', { start, end })
  }
  const duration = () => {
    if (props.entry.kind !== 'schedule') return undefined
    const schedule = task().schedule!
    const minutes = Math.max(
      0,
      Math.round(
        (new Date(schedule.ends_at).getTime() -
          new Date(schedule.starts_at).getTime()) /
          60_000,
      ),
    )
    if (minutes === 0) return undefined
    const hours = Math.floor(minutes / 60)
    const remainder = minutes % 60
    if (hours > 0 && remainder > 0) {
      return t('calendar.entries.durationHoursMinutes', {
        hours,
        minutes: remainder,
      })
    }
    return hours > 0
      ? t('calendar.entries.durationHours', { hours })
      : t('calendar.entries.durationMinutes', { minutes: remainder })
  }
  const positionStyle = () => {
    if (props.position === undefined) return undefined
    const { column, columnCount, entry } = props.position
    const gap = 3
    return {
      top: `${((entry.startMinute - (props.rangeStartMinute ?? 0)) / 60) * HOUR_HEIGHT}px`,
      height: `${Math.max(
        ((entry.endMinute - entry.startMinute) / 60) * HOUR_HEIGHT,
        HOUR_HEIGHT / 2,
      )}px`,
      left: `calc(${(column / columnCount) * 100}% + ${gap}px)`,
      width: `calc(${100 / columnCount}% - ${gap * 2}px)`,
    }
  }

  return (
    <button
      type="button"
      class={`calendar-entry calendar-entry--${props.entry.kind}`}
      classList={{
        'calendar-entry--completed': task().status === 'completed',
        'calendar-entry--cancelled': task().status === 'cancelled',
        'calendar-entry--conflict': task().kind === 'recurrence_conflict',
        'calendar-entry--short':
          props.entry.endMinute - props.entry.startMinute <= 60,
        'calendar-entry--very-short':
          props.entry.endMinute - props.entry.startMinute <= 30,
        [`calendar-entry--${task().priority}`]: true,
      }}
      style={positionStyle()}
      aria-label={t('calendar.openTask', {
        date: props.dateLabel,
        title: task().title,
      })}
      onClick={() => props.onOpen()}
    >
      <span class="calendar-entry-time">
        <Show when={props.entry.kind === 'schedule'} fallback={<Flag size={12} strokeWidth={2} />}>
          <Clock3 size={12} strokeWidth={2} />
        </Show>
        {time()}
      </span>
      <strong>{task().title}</strong>
      <span class="calendar-entry-meta">
        <span class={`calendar-priority calendar-priority--${task().priority}`}>
          {priorityLabel()}
        </span>
        <Show when={duration()}>{(value) => <span>{value()}</span>}</Show>
      </span>
      <Show when={task().kind === 'recurrence_conflict'}>
        <span class="calendar-entry-conflict">{t('calendar.entries.conflict')}</span>
      </Show>
    </button>
  )
}

function CalendarLoadingState() {
  const { t } = useI18n()
  return (
    <div class="calendar-loading" aria-label={t('calendar.states.loading')}>
      <LoaderCircle class="spin" size={22} strokeWidth={1.9} />
      <div>
        <For each={Array.from({ length: 7 })}>{() => <span />}</For>
      </div>
    </div>
  )
}
