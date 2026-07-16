import { describe, expect, it } from 'vitest'

import type { Task } from '@/entities/task/model'
import {
  buildCalendarEntries,
  buildCalendarWeek,
  calendarWeekKey,
  layoutCalendarEntries,
  resolveCalendarWeek,
  resolveCalendarTimeRange,
} from '@/features/calendar/calendar'

describe('calendar week', () => {
  it('covers Monday through Sunday around the selected date', () => {
    const week = resolveCalendarWeek('2026-07-15', new Date(2025, 0, 1))
    const calendar = buildCalendarWeek(week)

    expect(calendarWeekKey(calendar.weekStartsOn)).toBe('2026-07-13')
    expect(calendar.days).toHaveLength(7)
    expect(calendar.days[0].key).toBe('2026-07-13')
    expect(calendar.days.at(-1)?.key).toBe('2026-07-19')
    expect(calendar.startsAt).toBe('2026-07-13T00:00:00')
    expect(calendar.endsAt).toBe('2026-07-19T23:59:59')
  })

  it('shows every day crossed by a schedule and a distinct later deadline', () => {
    const calendar = buildCalendarWeek(new Date(2026, 6, 13))
    const task = createTask({
      due_at: '2026-07-19T18:00:00',
      schedule: {
        starts_at: '2026-07-14T09:00:00',
        ends_at: '2026-07-16T12:00:00',
      },
    })

    const entries = buildCalendarEntries([task], calendar)

    expect(entries.get('2026-07-14')?.[0].scheduleSegment).toBe('start')
    expect(entries.get('2026-07-14')?.[0].startMinute).toBe(9 * 60)
    expect(entries.get('2026-07-14')?.[0].endMinute).toBe(24 * 60)
    expect(entries.get('2026-07-15')?.[0].scheduleSegment).toBe('middle')
    expect(entries.get('2026-07-16')?.[0].scheduleSegment).toBe('end')
    expect(entries.get('2026-07-16')?.[0].endMinute).toBe(12 * 60)
    expect(entries.get('2026-07-19')?.[0].kind).toBe('deadline')
  })

  it('places overlapping entries beside each other without narrowing later work', () => {
    const calendar = buildCalendarWeek(new Date(2026, 6, 13))
    const entries = buildCalendarEntries(
      [
        scheduledTask('first', '09:00', '11:00'),
        scheduledTask('second', '10:00', '12:00'),
        scheduledTask('later', '13:00', '14:00'),
      ],
      calendar,
    ).get('2026-07-14')!

    const positioned = layoutCalendarEntries(entries)

    expect(positioned.map(({ column, columnCount, entry }) => ({
      column,
      columnCount,
      title: entry.task.title,
    }))).toEqual([
      { column: 0, columnCount: 2, title: 'first' },
      { column: 1, columnCount: 2, title: 'second' },
      { column: 0, columnCount: 1, title: 'later' },
    ])
  })

  it('keeps common daytime hours compact and expands for outlying work', () => {
    const calendar = buildCalendarWeek(new Date(2026, 6, 13))
    const daytimeEntries = buildCalendarEntries(
      [scheduledTask('daytime', '09:00', '19:00')],
      calendar,
    ).get('2026-07-14')!
    const extendedEntries = buildCalendarEntries(
      [
        scheduledTask('early', '05:30', '06:00'),
        scheduledTask('late', '21:30', '22:15'),
      ],
      calendar,
    ).get('2026-07-14')!

    expect(resolveCalendarTimeRange(daytimeEntries)).toEqual({
      startMinute: 7 * 60,
      endMinute: 21 * 60,
    })
    expect(resolveCalendarTimeRange(extendedEntries)).toEqual({
      startMinute: 4 * 60,
      endMinute: 24 * 60,
    })
  })
})

function scheduledTask(title: string, startsAt: string, endsAt: string): Task {
  return createTask({
    task_id: title,
    title,
    schedule: {
      starts_at: `2026-07-14T${startsAt}:00`,
      ends_at: `2026-07-14T${endsAt}:00`,
    },
  })
}

function createTask(overrides: Partial<Task> = {}): Task {
  return {
    task_id: 'calendar-task-id',
    title: 'Prepare the release',
    description: null,
    status: 'active',
    priority: 'normal',
    kind: 'regular',
    due_at: '2026-07-01T18:00:00',
    created_at: '2026-06-20T10:00:00',
    completed_at: null,
    schedule: null,
    tags: [],
    recurrence_id: null,
    ...overrides,
  }
}
