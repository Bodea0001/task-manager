import { QueryClient, QueryClientProvider } from '@tanstack/solid-query'
import { Route, Router } from '@solidjs/router'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@solidjs/testing-library'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/entities/task/model'
import { CalendarPage } from '@/pages/calendar/CalendarPage'
import { changeLocale } from '@/shared/i18n/config'
import { I18nProvider } from '@/shared/i18n/I18nProvider'

afterEach(async () => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
  await changeLocale('en')
})

describe('Calendar workspace', () => {
  it('selects the current day when returning to today', async () => {
    window.history.replaceState({}, '', '/calendar')
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(jsonResponse({ tasks: [], conflicts: [] })),
      ),
    )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <Router>
            <Route path="/calendar" component={CalendarPage} />
          </Router>
        </QueryClientProvider>
      </I18nProvider>
    ))

    const dayTabs = await screen.findAllByRole('tab', { hidden: true })
    const todayTab = dayTabs.find(
      (tab) => tab.getAttribute('aria-selected') === 'true',
    )
    const anotherDayTab = dayTabs.find((tab) => tab !== todayTab)
    expect(todayTab).toBeDefined()
    expect(anotherDayTab).toBeDefined()

    await fireEvent.click(anotherDayTab!)
    expect(anotherDayTab).toHaveAttribute('aria-selected', 'true')
    await fireEvent.click(screen.getByRole('button', { name: 'Today' }))

    await waitFor(() =>
      expect(todayTab).toHaveAttribute('aria-selected', 'true'),
    )
  })

  it('loads the visible range and preserves the selected week around task details', async () => {
    window.history.replaceState({}, '', '/calendar?week=2026-07-06')
    const deadlineTask = createTask({
      task_id: 'deadline-task-id',
      title: 'Submit the report',
      due_at: '2026-07-10T17:00:00',
      priority: 'high',
    })
    const scheduledTask = createTask({
      task_id: 'scheduled-task-id',
      title: 'Planning workshop',
      due_at: '2026-07-12T18:00:00',
      schedule: {
        starts_at: '2026-07-08T09:00:00',
        ends_at: '2026-07-08T11:00:00',
      },
    })
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const url = new URL(String(args[0]), 'http://localhost')
      if (url.pathname === '/api/v1/tasks' && url.searchParams.has('due_from')) {
        return Promise.resolve(
          jsonResponse({ tasks: [deadlineTask], conflicts: [] }),
        )
      }
      if (url.pathname === '/api/v1/tasks') {
        return Promise.resolve(
          jsonResponse({ tasks: [scheduledTask], conflicts: [] }),
        )
      }
      return Promise.resolve(jsonResponse({ tags: [] }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: 30_000 },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <Router>
            <Route path="/calendar" component={CalendarPage} />
          </Router>
        </QueryClientProvider>
      </I18nProvider>
    ))

    expect(
      await screen.findByRole('button', {
        name: 'Open Submit the report on July 10, 2026',
      }),
    ).toBeVisible()
    expect(
      screen.getByRole('button', {
        name: 'Open Planning workshop on July 8, 2026',
      }),
    ).toBeVisible()
    expect(screen.getAllByText('2h').length).toBeGreaterThan(0)
    expect(screen.getAllByText('High').length).toBeGreaterThan(0)

    await chooseOption('Priority All priorities', 'High')
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) => {
          const url = new URL(String(input), 'http://localhost')
          return url.searchParams.getAll('priorities').includes('high')
        }),
      ).toBe(true),
    )
    expect(
      screen.queryByRole('button', {
        name: 'Open Planning workshop on July 8, 2026',
      }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', {
        name: 'Open Submit the report on July 10, 2026',
      }),
    ).toBeVisible()

    await chooseOption('Priority High', 'Urgent')
    expect(
      await screen.findByText('No tasks match the selected filters.'),
    ).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: 'Reset filters' }))

    await fireEvent.click(
      screen.getByRole('tab', {
        name: /July 8, 2026, 1 task/,
        hidden: true,
      }),
    )
    const mobileDay = screen.getByRole('tabpanel', {
      name: /July 8, 2026, 1 task/,
      hidden: true,
    })
    expect(within(mobileDay).getByText(scheduledTask.title)).toBeInTheDocument()

    const taskRequests = fetchMock.mock.calls
      .map(([input]) => new URL(String(input), 'http://localhost'))
      .filter((url) => url.pathname === '/api/v1/tasks')
    expect(taskRequests.some((url) => url.searchParams.has('due_from'))).toBe(true)
    expect(
      taskRequests.some(
        (url) =>
          url.searchParams.has('starts_to') &&
          url.searchParams.has('ends_from'),
      ),
    ).toBe(true)

    await fireEvent.click(
      within(screen.getByRole('grid')).getByRole('button', {
        name: 'Open Planning workshop on July 8, 2026',
      }),
    )
    expect(
      await screen.findByRole('heading', { name: scheduledTask.title }),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: 'Back to calendar' })).toBeVisible()
    expect(new URLSearchParams(window.location.search).get('week')).toBe('2026-07-06')

    await fireEvent.click(screen.getByRole('button', { name: 'Back to calendar' }))
    expect(
      await screen.findByRole('button', {
        name: 'Open Planning workshop on July 8, 2026',
      }),
    ).toBeVisible()
    expect(new URLSearchParams(window.location.search).get('task')).toBeNull()

    await fireEvent.click(
      screen.getByRole('button', { name: 'Previous week' }),
    )
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get('week')).toBe(
        '2026-06-29',
      ),
    )
  })
})

async function chooseOption(triggerName: string, optionName: string) {
  await fireEvent.keyDown(screen.getByRole('button', { name: triggerName }), {
    key: 'ArrowDown',
  })
  await fireEvent.click(await screen.findByRole('option', { name: optionName }))
}

function createTask(overrides: Partial<Task> = {}): Task {
  return {
    task_id: 'calendar-task-id',
    title: 'Calendar task',
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

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status: 200,
  })
}
