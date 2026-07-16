import type { Task } from '@/entities/task/model'

export type CalendarEntryKind = 'deadline' | 'schedule'
export type CalendarScheduleSegment = 'single' | 'start' | 'middle' | 'end'

export interface CalendarDay {
  date: Date
  key: string
}

export interface CalendarWeek {
  days: readonly CalendarDay[]
  endsAt: string
  startsAt: string
  weekStartsOn: Date
}

export interface CalendarEntry {
  dateKey: string
  endMinute: number
  key: string
  kind: CalendarEntryKind
  scheduleSegment?: CalendarScheduleSegment
  startMinute: number
  task: Task
}

export interface PositionedCalendarEntry {
  column: number
  columnCount: number
  entry: CalendarEntry
}

export interface CalendarTimeRange {
  endMinute: number
  startMinute: number
}

const MINIMUM_ENTRY_MINUTES = 30
const DEFAULT_TIMELINE_START = 7 * 60
const DEFAULT_TIMELINE_END = 21 * 60

export function resolveCalendarWeek(value: string | undefined, today: Date): Date {
  const parsed = parseLocalDate(value)
  return startOfWeek(parsed || today)
}

export function calendarWeekKey(weekStartsOn: Date): string {
  return localDateKey(startOfWeek(weekStartsOn))
}

export function shiftCalendarWeek(weekStartsOn: Date, offset: number): Date {
  return addDays(startOfWeek(weekStartsOn), offset * 7)
}

export function buildCalendarWeek(weekStartsOn: Date): CalendarWeek {
  const firstDay = startOfWeek(weekStartsOn)
  const endExclusive = addDays(firstDay, 7)
  return {
    days: Array.from({ length: 7 }, (_, index) => {
      const date = addDays(firstDay, index)
      return { date, key: localDateKey(date) }
    }),
    endsAt: localDateTime(addMilliseconds(endExclusive, -1_000)),
    startsAt: localDateTime(firstDay),
    weekStartsOn: firstDay,
  }
}

export function buildCalendarEntries(
  tasks: readonly Task[],
  calendar: CalendarWeek,
): ReadonlyMap<string, readonly CalendarEntry[]> {
  const entries = new Map<string, CalendarEntry[]>()
  const rangeStart = calendar.days[0].date
  const rangeEnd = addDays(calendar.days.at(-1)!.date, 1)

  for (const task of tasks) {
    if (task.schedule === null) {
      addEntry(entries, deadlineEntry(task))
      continue
    }

    const scheduleStart = new Date(task.schedule.starts_at)
    const scheduleEnd = new Date(task.schedule.ends_at)
    const firstScheduleDay = startOfDay(scheduleStart)
    const lastScheduleDay = startOfDay(scheduleEnd)
    let currentDay = maxDate(firstScheduleDay, rangeStart)

    while (currentDay < rangeEnd && currentDay <= lastScheduleDay) {
      const dateKey = localDateKey(currentDay)
      addEntry(entries, {
        dateKey,
        endMinute: visualEndMinute(
          currentDay.getTime() === lastScheduleDay.getTime()
            ? minuteOfDay(scheduleEnd)
            : 24 * 60,
          currentDay.getTime() === firstScheduleDay.getTime()
            ? minuteOfDay(scheduleStart)
            : 0,
        ),
        key: `${task.task_id}:schedule:${dateKey}`,
        kind: 'schedule',
        scheduleSegment: scheduleSegment(
          currentDay,
          firstScheduleDay,
          lastScheduleDay,
        ),
        startMinute:
          currentDay.getTime() === firstScheduleDay.getTime()
            ? minuteOfDay(scheduleStart)
            : 0,
        task,
      })
      currentDay = addDays(currentDay, 1)
    }

    if (localDateKey(new Date(task.due_at)) !== localDateKey(scheduleStart)) {
      addEntry(entries, deadlineEntry(task))
    }
  }

  for (const dayEntries of entries.values()) {
    dayEntries.sort(compareEntries)
  }
  return entries
}

export function layoutCalendarEntries(
  entries: readonly CalendarEntry[],
): readonly PositionedCalendarEntry[] {
  const sorted = [...entries].sort(compareEntries)
  const positioned: PositionedCalendarEntry[] = []
  let group: { column: number; entry: CalendarEntry }[] = []
  let groupEnd = -1

  const commitGroup = () => {
    if (group.length === 0) return
    const columnCount = Math.max(...group.map((item) => item.column)) + 1
    positioned.push(
      ...group.map((item) => ({ ...item, columnCount })),
    )
    group = []
    groupEnd = -1
  }

  for (const entry of sorted) {
    if (group.length > 0 && entry.startMinute >= groupEnd) commitGroup()
    const columnEnds: number[] = []
    for (const item of group) {
      columnEnds[item.column] = Math.max(
        columnEnds[item.column] ?? 0,
        item.entry.endMinute,
      )
    }
    const availableColumn = columnEnds.findIndex(
      (endMinute) => endMinute <= entry.startMinute,
    )
    group.push({
      column: availableColumn === -1 ? columnEnds.length : availableColumn,
      entry,
    })
    groupEnd = Math.max(groupEnd, entry.endMinute)
  }
  commitGroup()
  return positioned
}

export function resolveCalendarTimeRange(
  entries: readonly CalendarEntry[],
): CalendarTimeRange {
  let startMinute = DEFAULT_TIMELINE_START
  let endMinute = DEFAULT_TIMELINE_END

  for (const entry of entries) {
    if (entry.startMinute < DEFAULT_TIMELINE_START) {
      startMinute = Math.min(
        startMinute,
        Math.max(0, Math.floor(entry.startMinute / 60) * 60 - 60),
      )
    }
    if (entry.endMinute > DEFAULT_TIMELINE_END) {
      endMinute = Math.max(
        endMinute,
        Math.min(24 * 60, Math.ceil(entry.endMinute / 60) * 60 + 60),
      )
    }
  }

  return { startMinute, endMinute }
}

export function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function parseLocalDate(value: string | undefined): Date | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '')
  if (match === null) {
    return undefined
  }
  const year = Number(match[1])
  const monthIndex = Number(match[2]) - 1
  const day = Number(match[3])
  const parsed = new Date(year, monthIndex, day)
  return parsed.getFullYear() === year &&
    parsed.getMonth() === monthIndex &&
    parsed.getDate() === day
    ? parsed
    : undefined
}

function deadlineEntry(task: Task): CalendarEntry {
  const deadline = new Date(task.due_at)
  const dateKey = localDateKey(deadline)
  const startMinute = minuteOfDay(deadline)
  return {
    dateKey,
    endMinute: visualEndMinute(startMinute, startMinute),
    key: `${task.task_id}:deadline:${dateKey}`,
    kind: 'deadline',
    startMinute,
    task,
  }
}

function scheduleSegment(
  day: Date,
  firstDay: Date,
  lastDay: Date,
): CalendarScheduleSegment {
  const isFirst = day.getTime() === firstDay.getTime()
  const isLast = day.getTime() === lastDay.getTime()
  if (isFirst && isLast) {
    return 'single'
  }
  if (isFirst) {
    return 'start'
  }
  return isLast ? 'end' : 'middle'
}

function addEntry(
  entries: Map<string, CalendarEntry[]>,
  entry: CalendarEntry,
): void {
  const dayEntries = entries.get(entry.dateKey) || []
  dayEntries.push(entry)
  entries.set(entry.dateKey, dayEntries)
}

function compareEntries(left: CalendarEntry, right: CalendarEntry): number {
  return entryTime(left) - entryTime(right)
}

function entryTime(entry: CalendarEntry): number {
  return entry.startMinute
}

function minuteOfDay(date: Date): number {
  return date.getHours() * 60 + date.getMinutes()
}

function visualEndMinute(endMinute: number, startMinute: number): number {
  return Math.min(24 * 60, Math.max(endMinute, startMinute + MINIMUM_ENTRY_MINUTES))
}

function startOfWeek(date: Date): Date {
  const day = startOfDay(date)
  return addDays(day, -((day.getDay() + 6) % 7))
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days)
}

function addMilliseconds(date: Date, milliseconds: number): Date {
  return new Date(date.getTime() + milliseconds)
}

function maxDate(left: Date, right: Date): Date {
  return left > right ? left : right
}

function localDateTime(date: Date): string {
  return `${localDateKey(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}
