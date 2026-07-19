import { Route, Router } from '@solidjs/router'
import { QueryClient, QueryClientProvider } from '@tanstack/solid-query'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@solidjs/testing-library'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ParentProps } from 'solid-js'

import { AppShell } from '@/app/AppShell'
import { ChatDraftProvider } from '@/features/chat/ChatDraftProvider'
import { changeLocale } from '@/shared/i18n/config'
import { I18nProvider } from '@/shared/i18n/I18nProvider'

beforeEach(async () => {
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState({}, '', '/')
  await changeLocale('en')
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ chats: [], next_offset: null }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    ),
  )
})

afterEach(() => vi.unstubAllGlobals())

describe('application navigation', () => {
  it('provides a keyboard shortcut to the main workspace', async () => {
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView
    HTMLElement.prototype.scrollIntoView = vi.fn()
    renderAppShell()

    const skipLink = screen.getByRole('link', {
      name: 'Skip to main content',
    })
    skipLink.focus()
    await fireEvent.click(skipLink)

    await waitFor(() => expect(screen.getByRole('main')).toHaveFocus())
    HTMLElement.prototype.scrollIntoView = originalScrollIntoView
  })

  it('allows the user to collapse and expand desktop navigation', async () => {
    renderAppShell()

    const collapseButton = screen.getByRole('button', {
      name: 'Collapse navigation',
    })
    await fireEvent.click(collapseButton)

    const expandButton = screen.getByRole('button', {
      name: 'Expand navigation',
    })
    await fireEvent.click(expandButton)

    expect(
      screen.getByRole('button', { name: 'Collapse navigation' }),
    ).toBeVisible()
  })

  it('starts loading recurring tasks before opening the workspace', async () => {
    renderAppShell()
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockClear()

    await fireEvent.mouseEnter(
      screen.getAllByRole('link', { name: 'Recurring tasks' })[0],
    )

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/recurrence-templates',
        expect.anything(),
      ),
    )
  })

  it('allows the user to collapse and restore the assistant panel', async () => {
    const firstRender = renderAppShell()

    await fireEvent.click(
      screen.getByRole('button', { name: 'Collapse assistant panel' }),
    )
    expect(
      screen.getByRole('button', { name: 'Expand assistant panel' }),
    ).toBeVisible()
    firstRender.unmount()

    renderAppShell()
    const expandButton = screen.getByRole('button', {
      name: 'Expand assistant panel',
    })
    await fireEvent.click(expandButton)

    expect(
      screen.queryByRole('button', { name: 'Expand assistant panel' }),
    ).not.toBeInTheDocument()
  })

  it('opens the assistant over the current mobile workspace and restores focus', async () => {
    renderAppShell()

    const openButton = screen.getByRole('button', { name: 'Open assistant' })
    expect(openButton).toHaveAttribute('aria-expanded', 'false')
    await fireEvent.click(openButton)

    const assistant = screen.getByRole('dialog', { name: 'Assistant' })
    expect(assistant).toBeInTheDocument()
    expect(screen.getByText('Task workspace')).toBeInTheDocument()
    const closeButton = within(assistant).getByRole('button', {
      name: 'Close assistant',
    })
    await waitFor(() => expect(closeButton).toHaveFocus())
    await fireEvent.click(closeButton)

    expect(openButton).toHaveAttribute('aria-expanded', 'false')
    await waitFor(() => expect(openButton).toHaveFocus())
  })
})

function renderAppShell() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(() => (
    <ChatDraftProvider userId="user-id">
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <Router root={TestAppShell}>
            <Route path="/" component={() => <div>Task workspace</div>} />
          </Router>
        </QueryClientProvider>
      </I18nProvider>
    </ChatDraftProvider>
  ))
}

function TestAppShell(props: ParentProps) {
  return <AppShell emailVerified>{props.children}</AppShell>
}
