import { QueryClient, QueryClientProvider } from '@tanstack/solid-query'
import { Route, Router } from '@solidjs/router'
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from '@solidjs/testing-library'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/entities/task/model'
import { TasksPage } from '@/pages/tasks/TasksPage'
import { changeLocale } from '@/shared/i18n/config'
import { I18nProvider } from '@/shared/i18n/I18nProvider'

afterEach(async () => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
  await changeLocale('en')
})

describe('Tasks workspace', () => {
  it('switches task views with the standard tabs keyboard controls', async () => {
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
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    const todayTab = screen.getByRole('tab', { name: 'Today' })
    const upcomingTab = screen.getByRole('tab', { name: 'Upcoming' })
    todayTab.focus()
    await fireEvent.keyDown(todayTab, { key: 'ArrowRight' })

    expect(upcomingTab).toHaveFocus()
    expect(upcomingTab).toHaveAttribute('aria-selected', 'true')
    await fireEvent.keyDown(upcomingTab, { key: 'End' })
    expect(screen.getByRole('tab', { name: 'Completed' })).toHaveFocus()
  })

  it('shows persisted tasks and removes a task after confirmed completion', async () => {
    const task = createCurrentTask()
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ tasks: [task], conflicts: [] }))
        .mockResolvedValueOnce(
          jsonResponse({
            ...task,
            status: 'completed',
            completed_at: new Date().toISOString(),
          }),
        ),
    )
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    expect(
      await screen.findByRole('heading', { name: task.title }),
    ).toBeVisible()

    await fireEvent.click(
      screen.getByRole('button', { name: `Complete ${task.title}` }),
    )

    await waitFor(() => {
      expect(
        screen.queryByRole('heading', { name: task.title }),
      ).not.toBeInTheDocument()
    })
  })

  it('allows a reopened task to be completed again without leaving the view', async () => {
    const completedTask = {
      ...createCurrentTask(),
      status: 'completed' as const,
      completed_at: new Date().toISOString(),
    }
    const activeTask = {
      ...completedTask,
      status: 'active' as const,
      completed_at: null,
    }
    let persistedTask: Task = completedTask
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input] = args
      if (String(input).endsWith('/reopen')) {
        persistedTask = activeTask
        return Promise.resolve(jsonResponse(activeTask))
      }
      if (String(input).endsWith('/complete')) {
        persistedTask = completedTask
        return Promise.resolve(jsonResponse(completedTask))
      }
      return Promise.resolve(
        jsonResponse({ tasks: [persistedTask], conflicts: [] }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    const allTasksTab = screen.getByRole('tab', { name: 'All' })
    await waitFor(() => expect(allTasksTab).toHaveTextContent('1'))
    await fireEvent.click(allTasksTab)
    await fireEvent.click(
      screen.getByRole('button', { name: `Reopen ${completedTask.title}` }),
    )

    const completeButton = await screen.findByRole('button', {
      name: `Complete ${completedTask.title}`,
    })
    expect(completeButton).toBeEnabled()
    await fireEvent.click(completeButton)

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([input]) =>
          String(input).endsWith('/complete'),
        ),
      ).toBe(true),
    )
    expect(
      fetchMock.mock.calls.some(([input]) => String(input).endsWith('/reopen')),
    ).toBe(true)
  })

  it('creates a task from the workspace and opens the confirmed result', async () => {
    const createdTag = {
      tag_id: 'planning-tag-id',
      name: 'Planning',
      created_at: new Date().toISOString(),
    }
    const createdTask = {
      ...createCurrentTask(),
      task_id: 'created-task-id',
      title: 'Prepare the release notes',
      priority: 'normal' as const,
      due_at: '2026-07-20T10:00:00',
      tags: [createdTag],
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      if (String(input) === '/api/v1/tasks' && init?.method === 'POST') {
        return Promise.resolve(jsonResponse(createdTask))
      }
      if (String(input) === '/api/v1/tags' && init?.method === 'POST') {
        return Promise.resolve(jsonResponse(createdTag))
      }
      if (String(input) === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: [] }))
      }
      if (String(input) === `/api/v1/tasks/${createdTask.task_id}`) {
        return Promise.resolve(jsonResponse(createdTask))
      }
      return Promise.resolve(jsonResponse({ tasks: [], conflicts: [] }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(screen.getByRole('button', { name: 'Add task' }))
    await fireEvent.input(screen.getByLabelText('Title'), {
      target: { value: createdTask.title },
    })
    await fireEvent.input(screen.getByRole('textbox', { name: 'Task deadline' }), {
      target: { value: '07/20/2026 10:00' },
    })
    await fireEvent.input(screen.getByLabelText('Find or create a tag'), {
      target: { value: createdTag.name },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Create tag' }))
    expect(
      await screen.findByRole('button', { name: createdTag.name }),
    ).toHaveAttribute('aria-pressed', 'true')
    await fireEvent.click(screen.getByRole('button', { name: 'Create task' }))

    const detailsHeading = await screen.findByRole('heading', {
      name: createdTask.title,
    })
    expect(detailsHeading).toBeVisible()
    await waitFor(() => expect(detailsHeading).toHaveFocus())
    expect(
      screen.getByRole('button', { name: 'Save changes' }),
    ).toBeDisabled()
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input) === '/api/v1/tasks' && init?.method === 'POST',
    )
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      title: createdTask.title,
      due_at: '2026-07-20T10:00',
      priority: 'normal',
      tag_ids: [createdTag.tag_id],
    })
    const createTagCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input) === '/api/v1/tags' && init?.method === 'POST',
    )
    expect(JSON.parse(String(createTagCall?.[1]?.body))).toEqual({
      name: createdTag.name,
    })
    expect(new URLSearchParams(window.location.search).get('task')).toBe(
      createdTask.task_id,
    )
    await fireEvent.click(screen.getByRole('button', { name: 'Back to tasks' }))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Tasks' })).toHaveFocus(),
    )
  })

  it('keeps task input and highlights fields rejected by the server', async () => {
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      if (String(input) === '/api/v1/tasks' && init?.method === 'POST') {
        return Promise.resolve(
          jsonResponse(
            {
              code: 'request_validation_error',
              message: 'Request validation failed',
              request_id: 'task-request-id',
              details: [
                {
                  location: ['body', 'title'],
                  message: 'Choose a more specific title',
                  type: 'value_error',
                },
              ],
            },
            422,
          ),
        )
      }
      if (String(input) === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: [] }))
      }
      return Promise.resolve(jsonResponse({ tasks: [], conflicts: [] }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(screen.getByRole('button', { name: 'Add task' }))
    const titleInput = screen.getByLabelText('Title')
    const dueAtInput = screen.getByRole('textbox', { name: 'Task deadline' })
    await fireEvent.input(titleInput, {
      target: { value: 'Prepare notes' },
    })
    await fireEvent.input(dueAtInput, {
      target: { value: '07/20/2026 10:00' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Create task' }))

    expect(await screen.findByText('Choose a more specific title')).toBeVisible()
    expect(titleInput).toHaveAttribute('aria-invalid', 'true')
    expect(titleInput).toHaveValue('Prepare notes')
    expect(dueAtInput).toHaveValue('07/20/2026 10:00')
    await fireEvent.click(screen.getByText('Technical details'))
    expect(screen.getByText('Request ID: task-request-id')).toBeVisible()
  })

  it('explains schedule conflicts while creating a task', async () => {
    const blockingTask = {
      ...createCurrentTask(),
      task_id: 'blocking-task-id',
      title: 'Existing meeting',
      due_at: '2026-07-20T12:00:00',
      schedule: {
        starts_at: '2026-07-20T11:00:00',
        ends_at: '2026-07-20T12:00:00',
      },
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (url === '/api/v1/tasks' && init?.method === 'POST') {
        return Promise.resolve(
          jsonResponse(
            {
              code: 'task_schedule_overlap',
              message: 'Task schedule overlaps another task',
              request_id: 'creation-conflict-request-id',
              details: [],
            },
            422,
          ),
        )
      }
      if (url === '/api/v1/schedules/availability') {
        return Promise.resolve(
          jsonResponse({
            can_add_task: false,
            blocking_tasks: [blockingTask],
          }),
        )
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: [] }))
      }
      return Promise.resolve(jsonResponse({ tasks: [], conflicts: [] }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(screen.getByRole('button', { name: 'Add task' }))
    await fireEvent.input(screen.getByLabelText('Title'), {
      target: { value: 'Conflicting task' },
    })
    await fireEvent.input(screen.getByRole('textbox', { name: 'Task deadline' }), {
      target: { value: '07/20/2026 11:30' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Add schedule' }))
    expect(
      screen.getByText(
        'The deadline remains separate from the schedule. The schedule is the time planned for working on the task.',
      ),
    ).toBeVisible()
    const startsAtInput = screen.getByRole('textbox', { name: 'Starts' })
    const endsAtInput = screen.getByRole('textbox', { name: 'Ends' })
    await fireEvent.input(startsAtInput, {
      target: { value: '07/20/2026 11:00' },
    })
    await fireEvent.input(endsAtInput, {
      target: { value: '07/20/2026 12:00' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Create task' }))

    expect(
      await screen.findByText(
        'This time overlaps another task. Choose a free interval.',
      ),
    ).toBeVisible()
    expect(await screen.findByText(blockingTask.title)).toBeVisible()
    expect(
      screen.queryByText('The task could not be created. Try again.'),
    ).not.toBeInTheDocument()
    expect(startsAtInput).toHaveValue('07/20/2026 11:00')
    expect(endsAtInput).toHaveValue('07/20/2026 12:00')
    await fireEvent.click(screen.getByText('Technical details'))
    expect(
      screen.getByText('Request ID: creation-conflict-request-id'),
    ).toBeVisible()
  })

  it('returns from task creation to the task workspace', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) =>
        Promise.resolve(
          String(input) === '/api/v1/tags'
            ? jsonResponse({ tags: [] })
            : jsonResponse({ tasks: [], conflicts: [] }),
        ),
      ),
    )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(screen.getByRole('button', { name: 'Add task' }))
    expect(
      await screen.findByRole('heading', { name: 'New task' }),
    ).toBeVisible()
    await fireEvent.click(
      screen.getAllByRole('button', { name: 'Back to tasks' })[0],
    )

    expect(
      await screen.findByRole('button', { name: 'Add task' }),
    ).toBeVisible()
    expect(new URLSearchParams(window.location.search).has('create')).toBe(false)
  })

  it('updates the visible task after saving changes in its details', async () => {
    const task = createCurrentTask()
    const updatedTask = {
      ...task,
      title: 'Publish the release checklist',
      priority: 'normal' as const,
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (url === '/api/v1/tasks') {
        return Promise.resolve(jsonResponse({ tasks: [task], conflicts: [] }))
      }
      if (init?.method === 'PATCH') {
        return Promise.resolve(jsonResponse(updatedTask))
      }
      return Promise.resolve(jsonResponse(task))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(screen.getByRole('tab', { name: 'All' }))
    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open details for ${task.title}`,
      }),
    )
    const titleInput = await screen.findByLabelText('Title')
    const saveButton = screen.getByRole('button', { name: 'Save changes' })
    expect(saveButton).toBeDisabled()
    await fireEvent.input(titleInput, { target: { value: updatedTask.title } })
    await fireEvent.keyDown(
      screen.getByRole('button', { name: 'Priority High' }),
      { key: 'ArrowDown' },
    )
    await fireEvent.click(
      await screen.findByRole('option', { name: 'Normal' }),
    )
    expect(saveButton).toBeEnabled()
    await fireEvent.click(saveButton)

    expect(
      await screen.findByRole('heading', { name: updatedTask.title }),
    ).toBeVisible()
    const updateCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input) === `/api/v1/tasks/${task.task_id}` &&
        init?.method === 'PATCH',
    )
    expect(JSON.parse(String(updateCall?.[1]?.body))).toEqual({
      title: updatedTask.title,
      priority: updatedTask.priority,
    })
  })

  it('applies schedule removal only after the task changes are saved', async () => {
    const task = createCurrentTask()
    const scheduledTask = {
      ...task,
      schedule: {
        starts_at: task.due_at,
        ends_at: task.due_at,
      },
    }
    const updatedTask = { ...scheduledTask, schedule: null }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (url === '/api/v1/tasks') {
        return Promise.resolve(
          jsonResponse({ tasks: [scheduledTask], conflicts: [] }),
        )
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: task.tags }))
      }
      if (
        url === `/api/v1/tasks/${task.task_id}/schedule` &&
        init?.method === 'DELETE'
      ) {
        return Promise.resolve(jsonResponse(updatedTask))
      }
      return Promise.resolve(jsonResponse(scheduledTask))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open details for ${task.title}`,
      }),
    )
    await fireEvent.click(
      await screen.findByRole('button', { name: 'Remove schedule' }),
    )

    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input) === `/api/v1/tasks/${task.task_id}/schedule` &&
          init?.method === 'DELETE',
      ),
    ).toBe(false)
    const saveButton = screen.getByRole('button', { name: 'Save changes' })
    expect(saveButton).toBeEnabled()
    await fireEvent.click(saveButton)

    await waitFor(() => expect(saveButton).toBeDisabled())
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input) === `/api/v1/tasks/${task.task_id}/schedule` &&
          init?.method === 'DELETE',
      ),
    ).toBe(true)
  })

  it('keeps schedule edits in place when the server reports an overlap', async () => {
    const task = {
      ...createCurrentTask(),
      due_at: '2026-07-20T18:00:00',
      schedule: {
        starts_at: '2026-07-16T09:00:00',
        ends_at: '2026-07-16T10:00:00',
      },
    }
    const blockingTask = {
      ...task,
      task_id: 'blocking-task-id',
      title: 'Team meeting',
      schedule: {
        starts_at: '2026-07-16T10:30:00',
        ends_at: '2026-07-16T11:30:00',
      },
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (url === '/api/v1/tasks') {
        return Promise.resolve(jsonResponse({ tasks: [task], conflicts: [] }))
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: task.tags }))
      }
      if (url === '/api/v1/schedules/availability') {
        return Promise.resolve(
          jsonResponse({
            can_add_task: false,
            blocking_tasks: [blockingTask],
          }),
        )
      }
      if (init?.method === 'PATCH') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              code: 'task_schedule_overlap',
              message: 'Task schedule overlaps another task',
              request_id: 'request-id',
              details: [],
            }),
            {
              headers: { 'Content-Type': 'application/json' },
              status: 422,
            },
          ),
        )
      }
      return Promise.resolve(jsonResponse(task))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(screen.getByRole('tab', { name: 'All' }))
    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open details for ${task.title}`,
      }),
    )
    const startsAtInput = await screen.findByRole('textbox', { name: 'Starts' })
    const endsAtInput = screen.getByRole('textbox', { name: 'Ends' })
    await fireEvent.input(startsAtInput, {
      target: { value: '07/16/2026 11:00' },
    })
    await fireEvent.input(endsAtInput, {
      target: { value: '07/16/2026 12:00' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(
      await screen.findByText(
        'This time overlaps another task. Choose a free interval.',
      ),
    ).toBeVisible()
    expect(await screen.findByText(blockingTask.title)).toBeVisible()
    await fireEvent.click(screen.getByText('Technical details'))
    expect(screen.getByText('Request ID: request-id')).toBeVisible()
    expect(startsAtInput).toHaveValue('07/16/2026 11:00')
    expect(endsAtInput).toHaveValue('07/16/2026 12:00')
    expect(
      fetchMock.mock.calls.filter(
        ([input, init]) =>
          String(input) === `/api/v1/tasks/${task.task_id}` &&
          init?.method === undefined,
      ),
    ).toHaveLength(1)
    const availabilityCall = fetchMock.mock.calls.find(
      ([input]) => String(input) === '/api/v1/schedules/availability',
    )
    expect(JSON.parse(String(availabilityCall?.[1]?.body))).toEqual({
      window: {
        starts_at: '2026-07-16T11:00',
        ends_at: '2026-07-16T12:00',
      },
    })
  })

  it('saves only changed tag assignments for an existing task', async () => {
    const task = createCurrentTask()
    const planningTag = {
      tag_id: 'planning-tag-id',
      name: 'Planning',
      created_at: new Date().toISOString(),
    }
    const taskWithoutTags = { ...task, tags: [] }
    const updatedTask = { ...task, tags: [planningTag] }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (url === '/api/v1/tasks') {
        return Promise.resolve(jsonResponse({ tasks: [task], conflicts: [] }))
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: [...task.tags, planningTag] }))
      }
      if (init?.method === 'DELETE') {
        return Promise.resolve(jsonResponse(taskWithoutTags))
      }
      if (init?.method === 'PUT') {
        return Promise.resolve(jsonResponse(updatedTask))
      }
      return Promise.resolve(jsonResponse(task))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open details for ${task.title}`,
      }),
    )
    await fireEvent.click(await screen.findByRole('button', { name: 'Release' }))
    await fireEvent.click(await screen.findByRole('button', { name: 'Planning' }))
    await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Save changes' }),
      ).toBeDisabled(),
    )
    const assignmentCalls = fetchMock.mock.calls.filter(([, init]) =>
      ['DELETE', 'PUT'].includes(init?.method || ''),
    )
    expect(
      assignmentCalls.map(([input, init]) => [String(input), init?.method]),
    ).toEqual([
      [`/api/v1/tasks/${task.task_id}/tags/${task.tags[0].tag_id}`, 'DELETE'],
      [`/api/v1/tasks/${task.task_id}/tags/${planningTag.tag_id}`, 'PUT'],
    ])
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === 'PATCH'),
    ).toBe(false)
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === '/api/v1/tags'),
    ).toHaveLength(1)
  })

  it('requires confirmation before deleting a tag from every task', async () => {
    const task = createCurrentTask()
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (url === '/api/v1/tasks') {
        return Promise.resolve(jsonResponse({ tasks: [task], conflicts: [] }))
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: task.tags }))
      }
      if (url === `/api/v1/tags/${task.tags[0].tag_id}` && init?.method === 'DELETE') {
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(jsonResponse(task))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open details for ${task.title}`,
      }),
    )
    await fireEvent.click(
      await screen.findByRole('button', { name: 'Delete tag Release' }),
    )

    expect(screen.getByText('Delete tag “Release”?')).toBeVisible()
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE'),
    ).toBe(false)
    await fireEvent.click(screen.getByRole('button', { name: 'Delete tag' }))

    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'Delete tag Release' }),
      ).not.toBeInTheDocument(),
    )
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input) === `/api/v1/tags/${task.tags[0].tag_id}` &&
          init?.method === 'DELETE',
      ),
    ).toBe(true)
    expect(
      screen.getByRole('button', { name: 'Save changes' }),
    ).toBeDisabled()
  })

  it('requires confirmation before deleting a task from its details', async () => {
    const task = createCurrentTask()
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      if (String(input) === '/api/v1/tasks') {
        return Promise.resolve(jsonResponse({ tasks: [task], conflicts: [] }))
      }
      if (init?.method === 'DELETE') {
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(jsonResponse(task))
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open details for ${task.title}`,
      }),
    )
    await screen.findByLabelText('Title')
    await fireEvent.click(screen.getByRole('button', { name: 'Delete task' }))

    expect(screen.getByText('Delete this task?')).toBeVisible()
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE'),
    ).toBe(false)
    await fireEvent.click(
      screen.getByRole('button', { name: 'Delete permanently' }),
    )

    await waitFor(() =>
      expect(
        screen.queryByRole('heading', { name: task.title }),
      ).not.toBeInTheDocument(),
    )
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE'),
    ).toBe(true)
  })

  it('restores the selected task view from the page address', async () => {
    window.history.replaceState({}, '', '/?view=completed')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({ tasks: [createCurrentTask()], conflicts: [] }),
      ),
    )
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TestTasksPage />
        </QueryClientProvider>
      </I18nProvider>
    ))

    expect(screen.getByRole('tab', { name: 'Completed' })).toHaveAttribute(
      'aria-selected',
      'true',
    )

    await fireEvent.click(screen.getByRole('tab', { name: 'All' }))
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get('view')).toBe(
        'all',
      ),
    )
  })
})

function TestTasksPage() {
  return (
    <Router>
      <Route path="/" component={TasksPage} />
    </Router>
  )
}

function createCurrentTask(): Task {
  const dueAt = new Date()
  dueAt.setHours(18, 0, 0, 0)

  return {
    task_id: 'task-id',
    title: 'Review the release checklist',
    description: null,
    status: 'active',
    priority: 'high',
    kind: 'regular',
    due_at: dueAt.toISOString(),
    created_at: new Date().toISOString(),
    completed_at: null,
    schedule: null,
    tags: [
      {
        tag_id: 'tag-id',
        name: 'Release',
        created_at: new Date().toISOString(),
      },
    ],
    recurrence_id: null,
  }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}
