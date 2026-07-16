import { QueryClient, QueryClientProvider } from '@tanstack/solid-query'
import { Route, Router } from '@solidjs/router'
import { fireEvent, render, screen, waitFor } from '@solidjs/testing-library'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { RecurrenceTemplate } from '@/entities/recurrence/model'
import { RecurringPage } from '@/pages/recurring/RecurringPage'
import { changeLocale } from '@/shared/i18n/config'
import { I18nProvider } from '@/shared/i18n/I18nProvider'

afterEach(async () => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
  await changeLocale('en')
})

describe('Recurring tasks workspace', () => {
  it('returns from recurring task creation to the workspace', async () => {
    window.history.replaceState({}, '', '/recurring')
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) =>
        Promise.resolve(
          String(input) === '/api/v1/tags'
            ? jsonResponse({ tags: [] })
            : jsonResponse({ templates: [] }),
        ),
      ),
    )
    renderRecurringPage()

    await fireEvent.click(
      await screen.findByRole('button', { name: 'New recurring task' }),
    )
    expect(
      await screen.findByRole('heading', { name: 'New recurring task' }),
    ).toBeVisible()
    await fireEvent.click(
      screen.getAllByRole('button', { name: 'Back to recurring tasks' })[0],
    )

    expect(
      await screen.findByRole('button', { name: 'New recurring task' }),
    ).toBeVisible()
    expect(new URLSearchParams(window.location.search).has('create')).toBe(false)
  })

  it('finds a recurring task and explains its repeat rules', async () => {
    window.history.replaceState({}, '', '/recurring')
    const template = createTemplate()
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (isOccurrenceListRequest(url)) {
        return Promise.resolve(jsonResponse({ occurrences: [] }))
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: template.tags }))
      }
      return Promise.resolve(jsonResponse({ templates: [template] }))
    }))
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    render(() => (
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <Router>
            <Route path="/recurring" component={RecurringPage} />
          </Router>
        </QueryClientProvider>
      </I18nProvider>
    ))

    const openButton = await screen.findByRole('button', {
      name: `Open recurring task ${template.title}`,
    })
    expect(openButton).toHaveTextContent('2 rules')
    expect(openButton).toHaveTextContent('High priority')

    const searchInput = screen.getByRole('searchbox', {
      name: 'Search recurring tasks',
    })
    await fireEvent.input(searchInput, { target: { value: 'missing' } })
    expect(screen.getByText('No matching recurring tasks')).toBeVisible()
    await fireEvent.input(searchInput, { target: { value: 'health' } })
    const filteredOpenButton = screen.getByRole('button', {
      name: `Open recurring task ${template.title}`,
    })
    expect(filteredOpenButton).toBeVisible()

    await fireEvent.click(filteredOpenButton)

    expect(
      await screen.findByRole('heading', { name: template.title }),
    ).toBeVisible()
    expect(screen.getByText('Every 2 weeks')).toBeVisible()
    expect(screen.getByText('Ends after 5 occurrences')).toBeVisible()
    expect(screen.getByText('Health')).toBeVisible()
    expect(
      screen.getByRole('heading', { name: 'Description' }).parentElement,
    ).toHaveTextContent('Take after breakfast.')
    expect(new URLSearchParams(window.location.search).get('template')).toBe(
      template.template_id,
    )

    await fireEvent.click(
      screen.getByRole('button', { name: 'Back to recurring tasks' }),
    )
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get('template')).toBeNull(),
    )
    expect(
      screen.getByRole('button', {
        name: `Open recurring task ${template.title}`,
      }),
    ).toBeVisible()
  })

  it('explains tag impact and requires confirmation before changing instances', async () => {
    window.history.replaceState({}, '', '/recurring')
    const template = createTemplate()
    const workTag = {
      tag_id: 'work-tag-id',
      name: 'Work',
      created_at: '2026-07-02T08:00:00',
    }
    const fitnessTag = {
      tag_id: 'fitness-tag-id',
      name: 'Fitness',
      created_at: '2026-07-02T09:00:00',
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (isOccurrenceListRequest(url)) {
        return Promise.resolve(jsonResponse({ occurrences: [] }))
      }
      if (url === '/api/v1/recurrence-templates') {
        return Promise.resolve(jsonResponse({ templates: [template] }))
      }
      if (url === '/api/v1/tags') {
        if (init?.method === 'POST') {
          return Promise.resolve(jsonResponse(fitnessTag))
        }
        return Promise.resolve(
          jsonResponse({ tags: [...template.tags, workTag] }),
        )
      }
      if (url.endsWith(`/tags/${workTag.tag_id}`) && init?.method === 'PUT') {
        return Promise.resolve(
          jsonResponse({ ...template, tags: [...template.tags, workTag] }),
        )
      }
      if (
        url.endsWith(`/tags/${template.tags[0].tag_id}`) &&
        init?.method === 'DELETE'
      ) {
        return Promise.resolve(jsonResponse({ ...template, tags: [] }))
      }
      if (url.endsWith(`/tags/${fitnessTag.tag_id}`) && init?.method === 'PUT') {
        return Promise.resolve(
          jsonResponse({ ...template, tags: [...template.tags, fitnessTag] }),
        )
      }
      return Promise.resolve(jsonResponse(template))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderRecurringPage()

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open recurring task ${template.title}`,
      }),
    )
    expect(
      await screen.findByText(
        /Tag changes apply to the template, current active instances/,
      ),
    ).toBeVisible()

    await fireEvent.click(
      await screen.findByRole('button', { name: 'Add Work' }),
    )
    expect(
      screen.getByText(
        'The tag will be added to current active instances and future tasks from this template.',
      ),
    ).toBeVisible()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(
      false,
    )
    await fireEvent.click(screen.getByRole('button', { name: 'Add tag' }))
    expect(
      await screen.findByRole('button', { name: 'Remove Work' }),
    ).toBeVisible()

    await fireEvent.click(screen.getByRole('button', { name: 'Remove Health' }))
    expect(
      screen.getByText(/Past and completed tasks will not change/),
    ).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: 'Remove tag' }))

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE'),
      ).toBe(true),
    )

    await fireEvent.input(
      screen.getByRole('textbox', { name: 'Find or create a tag' }),
      { target: { value: fitnessTag.name } },
    )
    await fireEvent.click(
      screen.getByRole('button', { name: 'Create and add tag' }),
    )
    expect(screen.getByText(`Create and add “${fitnessTag.name}”?`)).toBeVisible()
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input) === '/api/v1/tags' && init?.method === 'POST',
      ),
    ).toBe(false)
    await fireEvent.click(
      screen.getByRole('button', { name: 'Confirm creation and addition' }),
    )
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input).endsWith(`/tags/${fitnessTag.tag_id}`) &&
            init?.method === 'PUT',
        ),
      ).toBe(true),
    )
  })

  it('confirms creation and updates only the mutable fields of a repeat rule', async () => {
    window.history.replaceState({}, '', '/recurring')
    const template = createTemplate()
    const createdRule = {
      recurrence_id: 'daily-rule-id',
      template_id: template.template_id,
      frequency: 'daily' as const,
      interval: 1,
      anchor_date: '2026-07-20',
      default_time: '10:00:00',
      default_duration: 'PT1H',
      weekdays: [],
      month_rule: null,
      schedule: {
        starts_at: '2026-07-20T10:00',
        ends_at: '2026-07-20T11:00',
      },
      repeat_until: null,
      occurrences_limit: null,
    }
    const updatedRule = {
      ...template.rules[0],
      anchor_date: '2026-07-20',
      default_time: '12:00:00',
      schedule: {
        starts_at: '2026-07-20T12:00',
        ends_at: '2026-07-20T12:15',
      },
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (isOccurrenceListRequest(url)) {
        return Promise.resolve(jsonResponse({ occurrences: [] }))
      }
      if (url === '/api/v1/recurrence-templates') {
        return Promise.resolve(jsonResponse({ templates: [template] }))
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: template.tags }))
      }
      if (
        url === `/api/v1/recurrence-templates/${template.template_id}/rules` &&
        init?.method === 'POST'
      ) {
        return Promise.resolve(jsonResponse(createdRule))
      }
      if (
        url === `/api/v1/recurrence-rules/${template.rules[0].recurrence_id}` &&
        init?.method === 'PATCH'
      ) {
        return Promise.resolve(jsonResponse(updatedRule))
      }
      return Promise.resolve(jsonResponse(template))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderRecurringPage()

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open recurring task ${template.title}`,
      }),
    )
    await fireEvent.click(
      await screen.findByRole('button', { name: 'Add rule' }),
    )
    await fireEvent.input(
      screen.getByRole('textbox', { name: 'First occurrence date' }),
      {
        target: { value: '07/20/2026' },
      },
    )
    await fireEvent.input(screen.getByRole('textbox', { name: 'Deadline time' }), {
      target: { value: '10:00' },
    })
    await fireEvent.click(
      screen.getByRole('switch', { name: 'Reserve a time block' }),
    )
    const durationMinutes = screen.getByRole('textbox', { name: 'Minutes' })
    await fireEvent.input(durationMinutes, { target: { value: '75' } })
    expect(durationMinutes).toHaveValue('59')
    await fireEvent.input(durationMinutes, { target: { value: '5900423' } })
    expect(durationMinutes).toHaveValue('59')
    await fireEvent.click(
      screen.getByRole('button', { name: 'Review change' }),
    )
    expect(screen.getByText('Create this repeat rule?')).toBeVisible()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(
      false,
    )
    await fireEvent.click(screen.getByRole('button', { name: 'Create rule' }))

    await waitFor(() =>
      expect(screen.queryByText('New repeat rule')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('Daily')).toBeVisible()
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).endsWith('/rules') && init?.method === 'POST',
    )
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      frequency: 'daily',
      interval: 1,
      anchor_date: '2026-07-20',
      default_time: '10:00',
      default_duration: 'PT1H59M',
      weekdays: [],
      month_rule: null,
    })

    await fireEvent.click(
      screen.getByRole('button', { name: 'Edit Weekly rule' }),
    )
    await fireEvent.input(
      screen.getByRole('textbox', { name: 'First occurrence date' }),
      { target: { value: '07/20/2026' } },
    )
    await fireEvent.input(screen.getByRole('textbox', { name: 'Deadline time' }), {
      target: { value: '12:00' },
    })
    await fireEvent.click(
      screen.getByRole('button', { name: 'Review change' }),
    )
    expect(screen.getByText('Apply these rule changes?')).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: 'Save rule' }))

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            String(input).includes('/recurrence-rules/') &&
            init?.method === 'PATCH',
        ),
      ).toBe(true),
    )
    const updateCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).includes('/recurrence-rules/') && init?.method === 'PATCH',
    )
    expect(JSON.parse(String(updateCall?.[1]?.body))).toEqual({
      anchor_date: '2026-07-20',
      default_time: '12:00',
      default_duration: 'PT15M',
      occurrences_limit: 5,
    })
  })

  it('creates a recurring task only after reviewing its first rule', async () => {
    window.history.replaceState({}, '', '/recurring')
    const createdTemplate: RecurrenceTemplate = {
      ...createTemplate(),
      template_id: 'created-template-id',
      title: 'Morning planning',
      description: null,
      priority: 'normal',
      tags: [],
      rules: [
        {
          ...createTemplate().rules[0],
          recurrence_id: 'created-rule-id',
          template_id: 'created-template-id',
          frequency: 'daily',
          interval: 1,
        },
      ],
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (isOccurrenceListRequest(url)) {
        return Promise.resolve(jsonResponse({ occurrences: [] }))
      }
      if (url === '/api/v1/recurrence-templates' && init?.method === 'POST') {
        return Promise.resolve(jsonResponse(createdTemplate))
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: [] }))
      }
      return Promise.resolve(jsonResponse({ templates: [] }))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderRecurringPage()

    await fireEvent.click(
      await screen.findByRole('button', { name: 'New recurring task' }),
    )
    await fireEvent.input(
      screen.getByRole('textbox', { name: 'Task name' }),
      { target: { value: createdTemplate.title } },
    )
    await fireEvent.click(
      screen.getByRole('button', { name: 'Review recurring task' }),
    )

    expect(screen.getByText('Create this recurring task?')).toBeVisible()
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === 'POST'),
    ).toBe(false)

    await fireEvent.click(
      screen.getByRole('button', { name: 'Create recurring task' }),
    )
    expect(
      await screen.findByRole('heading', { name: createdTemplate.title }),
    ).toBeVisible()

    const creationCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input) === '/api/v1/recurrence-templates' &&
        init?.method === 'POST',
    )
    const body = JSON.parse(String(creationCall?.[1]?.body))
    expect(body.title).toBe(createdTemplate.title)
    expect(body.priority).toBe('normal')
    expect(body.rules).toHaveLength(1)
    expect(body.rules[0]).toMatchObject({
      frequency: 'daily',
      interval: 1,
      default_duration: null,
      weekdays: [],
      month_rule: null,
    })
    expect(body.rules[0].anchor_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(body.rules[0].default_time).toMatch(/^\d{2}:\d{2}$/)
    expect(body.rules[0]).not.toHaveProperty('schedule')
  })

  it('creates a monthly ordinal-weekday rule through the calendar controls', async () => {
    window.history.replaceState({}, '', '/recurring')
    const template = createTemplate()
    const createdRule = {
      recurrence_id: 'ordinal-rule-id',
      template_id: template.template_id,
      frequency: 'monthly' as const,
      interval: 1,
      anchor_date: '2026-08-01',
      default_time: '09:00:00',
      default_duration: null,
      weekdays: [],
      month_rule: {
        month_day: null,
        week_of_month: -1 as const,
        weekday: 5 as const,
        business_day_policy: 'next_business_day' as const,
      },
      schedule: null,
      repeat_until: null,
      occurrences_limit: null,
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (isOccurrenceListRequest(url)) {
        return Promise.resolve(jsonResponse({ occurrences: [] }))
      }
      if (url === '/api/v1/recurrence-templates') {
        return Promise.resolve(jsonResponse({ templates: [template] }))
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: template.tags }))
      }
      if (url.endsWith('/rules') && init?.method === 'POST') {
        return Promise.resolve(jsonResponse(createdRule))
      }
      return Promise.resolve(jsonResponse(template))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderRecurringPage()

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open recurring task ${template.title}`,
      }),
    )
    await fireEvent.click(
      await screen.findByRole('button', { name: 'Add rule' }),
    )
    await chooseOption('Frequency Daily', 'Monthly')
    await chooseOption('Monthly pattern Day of month', 'Weekday position')
    await chooseOption('Week of month first', 'last')
    await chooseOption(/^Weekday /, 'Friday')
    await chooseOption(
      'Weekend handling Keep the calendar date',
      'Move to the next weekday',
    )
    await fireEvent.input(
      screen.getByRole('textbox', { name: 'First occurrence date' }),
      { target: { value: '08/01/2026' } },
    )
    await fireEvent.input(screen.getByRole('textbox', { name: 'Deadline time' }), {
      target: { value: '09:00' },
    })
    await fireEvent.click(
      screen.getByRole('button', { name: 'Review change' }),
    )
    await fireEvent.click(screen.getByRole('button', { name: 'Create rule' }))

    await waitFor(() =>
      expect(screen.queryByText('New repeat rule')).not.toBeInTheDocument(),
    )
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith('/rules') && init?.method === 'POST',
    )
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      frequency: 'monthly',
      interval: 1,
      anchor_date: '2026-08-01',
      default_time: '09:00',
      default_duration: null,
      weekdays: [],
      month_rule: {
        month_day: null,
        week_of_month: -1,
        weekday: 5,
        business_day_policy: 'next_business_day',
      },
    })
  })

  it('changes and skips one generated task without changing its repeat rule', async () => {
    window.history.replaceState({}, '', '/recurring')
    const template = createTemplate()
    const occurrence = {
      recurrence_id: template.rules[0].recurrence_id,
      task_id: 'generated-task-id',
      original_starts_at: '2026-07-20T08:00:00',
      due_at: '2026-07-20T08:00:00',
      schedule: null,
      is_cancelled: false,
    }
    const changedOccurrence = {
      ...occurrence,
      due_at: '2026-07-20T09:00:00',
    }
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (url === '/api/v1/recurrence-templates') {
        return Promise.resolve(jsonResponse({ templates: [template] }))
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: template.tags }))
      }
      if (isOccurrenceListRequest(url)) {
        return Promise.resolve(jsonResponse({ occurrences: [occurrence] }))
      }
      if (url.endsWith('/skip') && init?.method === 'POST') {
        return Promise.resolve(
          jsonResponse({ ...changedOccurrence, is_cancelled: true }),
        )
      }
      if (url.includes('/occurrences/') && init?.method === 'PATCH') {
        return Promise.resolve(jsonResponse(changedOccurrence))
      }
      return Promise.resolve(jsonResponse(template))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderRecurringPage()

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open recurring task ${template.title}`,
      }),
    )
    expect(
      await screen.findByRole('button', { name: 'Edit task instance' }),
    ).toBeVisible()
    expect(
      fetchMock.mock.calls.some(([input]) => {
        const url = String(input)
        return (
          isOccurrenceListRequest(url) &&
          url.includes('starts_at=') &&
          url.includes('ends_at=')
        )
      }),
    ).toBe(true)

    await fireEvent.click(
      screen.getByRole('button', { name: 'Edit task instance' }),
    )
    await fireEvent.input(screen.getByRole('textbox', { name: 'Deadline' }), {
      target: { value: '07/20/2026 09:00' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Save instance' }))

    await waitFor(() => {
      const updateCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          String(input).includes('/occurrences/') && init?.method === 'PATCH',
      )
      expect(JSON.parse(String(updateCall?.[1]?.body))).toEqual({
        due_at: '2026-07-20T09:00',
      })
    })

    const skipButton = screen.getByRole('button', { name: 'Skip task instance' })
    await waitFor(() => expect(skipButton).toBeEnabled())
    await fireEvent.click(skipButton)
    expect(screen.getByText('Skip this task instance?')).toBeVisible()
    await fireEvent.click(screen.getByRole('button', { name: 'Skip instance' }))

    expect(
      await screen.findByRole('button', { name: 'Restore task instance' }),
    ).toBeVisible()
    expect(screen.getByText('Skipped')).toBeVisible()
    expect(
      fetchMock.mock.calls.some(
        ([input, init]) =>
          String(input).endsWith('/skip') && init?.method === 'POST',
      ),
    ).toBe(true)

    await fireEvent.click(
      screen.getByRole('button', { name: 'Restore task instance' }),
    )
    expect(screen.getByText('Restore this task instance?')).toBeVisible()
    await fireEvent.click(
      screen.getByRole('button', { name: 'Restore instance' }),
    )
    expect(
      await screen.findByRole('button', { name: 'Skip task instance' }),
    ).toBeVisible()
    const updateCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        String(input).includes('/occurrences/') && init?.method === 'PATCH',
    )
    expect(JSON.parse(String(updateCalls.at(-1)?.[1]?.body))).toEqual({
      status: 'active',
      due_at: changedOccurrence.due_at,
    })
  })

  it('keeps a large instance list bounded and navigable', async () => {
    window.history.replaceState({}, '', '/recurring')
    const template = createTemplate()
    const occurrences = Array.from({ length: 10 }, (_, index) => ({
      recurrence_id: template.rules[0].recurrence_id,
      task_id: `generated-task-${index}`,
      original_starts_at: `2026-07-${String(index + 16).padStart(2, '0')}T08:00:00`,
      due_at: `2026-07-${String(index + 16).padStart(2, '0')}T08:00:00`,
      schedule: null,
      is_cancelled: false,
    }))
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        if (url === '/api/v1/recurrence-templates') {
          return Promise.resolve(jsonResponse({ templates: [template] }))
        }
        if (url === '/api/v1/tags') {
          return Promise.resolve(jsonResponse({ tags: template.tags }))
        }
        if (isOccurrenceListRequest(url)) {
          return Promise.resolve(jsonResponse({ occurrences }))
        }
        return Promise.resolve(jsonResponse(template))
      }),
    )
    renderRecurringPage()

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open recurring task ${template.title}`,
      }),
    )
    const pagination = await screen.findByRole('navigation', {
      name: 'Task instance pages',
    })
    const firstPageText = pagination.textContent
    expect(
      screen.getAllByRole('button', { name: 'Edit task instance' }).length,
    ).toBeLessThan(occurrences.length)

    await fireEvent.click(
      screen.getByRole('button', { name: 'Next task instances' }),
    )
    await waitFor(() => expect(pagination.textContent).not.toBe(firstPageText))
    expect(
      screen.getAllByRole('button', { name: 'Edit task instance' }).length,
    ).toBeLessThan(occurrences.length)
  })

  it('explains and confirms rule and recurring task deletion', async () => {
    window.history.replaceState({}, '', '/recurring')
    const template = createTemplate()
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input, init] = args
      const url = String(input)
      if (isOccurrenceListRequest(url)) {
        return Promise.resolve(jsonResponse({ occurrences: [] }))
      }
      if (url === '/api/v1/recurrence-templates') {
        return Promise.resolve(jsonResponse({ templates: [template] }))
      }
      if (url === '/api/v1/tags') {
        return Promise.resolve(jsonResponse({ tags: template.tags }))
      }
      if (init?.method === 'DELETE') {
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(jsonResponse(template))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderRecurringPage()

    await fireEvent.click(
      await screen.findByRole('button', {
        name: `Open recurring task ${template.title}`,
      }),
    )
    await fireEvent.click(
      await screen.findByRole('button', { name: 'Delete Weekly rule' }),
    )
    expect(
      screen.getByText(/Unfinished task instances belonging to this rule/),
    ).toBeVisible()
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE'),
    ).toBe(false)

    await fireEvent.click(screen.getByRole('button', { name: 'Delete rule' }))
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'Delete Weekly rule' }),
      ).not.toBeInTheDocument(),
    )

    await fireEvent.click(
      screen.getByRole('button', { name: 'Delete recurring task' }),
    )
    expect(
      screen.getByText(/every unfinished generated instance/),
    ).toBeVisible()
    await fireEvent.click(
      screen.getAllByRole('button', { name: 'Delete recurring task' })[1],
    )

    await waitFor(() =>
      expect(
        screen.queryByRole('heading', { name: template.title }),
      ).not.toBeInTheDocument(),
    )
    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === 'DELETE'),
    ).toHaveLength(2)
  })
})

function renderRecurringPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  render(() => (
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <Router>
          <Route path="/recurring" component={RecurringPage} />
        </Router>
      </QueryClientProvider>
    </I18nProvider>
  ))
}

async function chooseOption(triggerName: string | RegExp, optionName: string) {
  await fireEvent.keyDown(screen.getByRole('button', { name: triggerName }), {
    key: 'ArrowDown',
  })
  await fireEvent.click(await screen.findByRole('option', { name: optionName }))
}

function createTemplate(): RecurrenceTemplate {
  return {
    template_id: 'template-id',
    title: 'Take vitamins',
    description: 'Take **after breakfast**.',
    priority: 'high',
    created_at: '2026-07-10T08:00:00',
    tags: [
      {
        tag_id: 'health-tag-id',
        name: 'Health',
        created_at: '2026-07-01T08:00:00',
      },
    ],
    rules: [
      {
        recurrence_id: 'weekly-rule-id',
        template_id: 'template-id',
        frequency: 'weekly',
        interval: 2,
        anchor_date: '2026-07-13',
        default_time: '08:00:00',
        default_duration: 'PT15M',
        weekdays: [1, 3, 5],
        month_rule: null,
        schedule: {
          starts_at: '2026-07-13T08:00:00',
          ends_at: '2026-07-13T08:15:00',
        },
        repeat_until: null,
        occurrences_limit: 5,
      },
      {
        recurrence_id: 'monthly-rule-id',
        template_id: 'template-id',
        frequency: 'monthly',
        interval: 1,
        anchor_date: '2026-08-01',
        default_time: '09:00:00',
        default_duration: null,
        weekdays: [],
        month_rule: {
          month_day: 1,
          week_of_month: null,
          weekday: null,
          business_day_policy: 'none',
        },
        schedule: null,
        repeat_until: null,
        occurrences_limit: null,
      },
    ],
  }
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status: 200,
  })
}

function isOccurrenceListRequest(url: string): boolean {
  return url.includes('/occurrences?')
}
