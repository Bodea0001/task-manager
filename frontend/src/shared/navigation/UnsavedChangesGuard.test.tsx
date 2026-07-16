import { A, Route, Router, useNavigate } from '@solidjs/router'
import { fireEvent, render, screen, waitFor } from '@solidjs/testing-library'
import { createSignal } from 'solid-js'
import { afterEach, describe, expect, it } from 'vitest'

import { changeLocale } from '@/shared/i18n/config'
import { I18nProvider } from '@/shared/i18n/I18nProvider'
import {
  createUnsavedChangesGuard,
  UnsavedChangesDialog,
} from '@/shared/navigation/UnsavedChangesGuard'

afterEach(async () => {
  window.history.replaceState({}, '', '/')
  await changeLocale('en')
})

describe('Unsaved changes protection', () => {
  it('keeps a changed form open until the user chooses to discard it', async () => {
    renderGuardedRoutes()

    await fireEvent.input(screen.getByRole('textbox', { name: 'Draft' }), {
      target: { value: 'Unsaved value' },
    })
    const destinationLink = screen.getByRole('link', {
      name: 'Another section',
    })
    destinationLink.focus()
    await fireEvent.click(destinationLink)

    expect(
      screen.getByRole('alertdialog', { name: 'Discard unsaved changes?' }),
    ).toBeVisible()
    expect(screen.getByRole('textbox', { name: 'Draft' })).toHaveValue(
      'Unsaved value',
    )

    const keepEditing = screen.getByRole('button', { name: 'Keep editing' })
    const discardChanges = screen.getByRole('button', {
      name: 'Discard changes',
    })
    await waitFor(() => expect(keepEditing).toHaveFocus())
    await fireEvent.keyDown(keepEditing, { key: 'Tab', shiftKey: true })
    expect(discardChanges).toHaveFocus()
    await fireEvent.keyDown(discardChanges, { key: 'Tab' })
    expect(keepEditing).toHaveFocus()
    await fireEvent.keyDown(keepEditing, { key: 'Escape' })
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    await waitFor(() => expect(destinationLink).toHaveFocus())

    await fireEvent.click(destinationLink)
    await fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))

    expect(screen.getByRole('heading', { name: 'Another section' })).toBeVisible()
  })

  it('does not prompt again after an explicit cancellation', async () => {
    renderGuardedRoutes()

    await fireEvent.input(screen.getByRole('textbox', { name: 'Draft' }), {
      target: { value: 'Unsaved value' },
    })
    await fireEvent.click(screen.getByRole('button', { name: 'Cancel editing' }))

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Another section' })).toBeVisible()
  })
})

function renderGuardedRoutes() {
  return render(() => (
    <I18nProvider>
      <Router>
        <Route path="/" component={GuardedForm} />
        <Route path="/destination" component={Destination} />
      </Router>
    </I18nProvider>
  ))
}

function GuardedForm() {
  const navigate = useNavigate()
  const [draft, setDraft] = createSignal('')
  const guard = createUnsavedChangesGuard(() => draft().length > 0)

  return (
    <main>
      <label>
        Draft
        <input
          value={draft()}
          onInput={(event) => setDraft(event.currentTarget.value)}
        />
      </label>
      <A href="/destination">Another section</A>
      <button
        type="button"
        onClick={() => {
          guard.allowNextNavigation()
          navigate('/destination')
        }}
      >
        Cancel editing
      </button>
      <UnsavedChangesDialog controller={guard} />
    </main>
  )
}

function Destination() {
  return <h1>Another section</h1>
}
