import { cleanup, fireEvent, render, screen, waitFor } from '@solidjs/testing-library'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ThemeSettings } from '@/features/theme-settings/ThemeSettings'
import { changeLocale, initializeI18n } from '@/shared/i18n/config'
import { I18nProvider } from '@/shared/i18n/I18nProvider'
import { ThemeProvider } from '@/shared/theme/ThemeProvider'

beforeEach(async () => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.removeProperty('color-scheme')
  await initializeI18n()
  await changeLocale('en')
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('theme preferences', () => {
  it('uses the system theme by default and follows system changes', async () => {
    const systemTheme = mockSystemTheme(true)
    renderThemeSettings()

    expect(screen.getByRole('button', { name: 'System' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(document.documentElement.dataset.theme).toBe('system')
    expect(document.documentElement.style.colorScheme).toBe('dark')

    systemTheme.setDark(false)

    await waitFor(() => {
      expect(document.documentElement.style.colorScheme).toBe('light')
    })
  })

  it('persists an explicit theme across application mounts', async () => {
    mockSystemTheme(true)
    const firstRender = renderThemeSettings()

    await fireEvent.click(screen.getByRole('button', { name: 'Light' }))
    expect(document.documentElement.dataset.theme).toBe('light')
    firstRender.unmount()

    renderThemeSettings()

    expect(screen.getByRole('button', { name: 'Light' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(document.documentElement.style.colorScheme).toBe('light')
  })
})

function renderThemeSettings() {
  return render(() => (
    <ThemeProvider>
      <I18nProvider>
        <ThemeSettings />
      </I18nProvider>
    </ThemeProvider>
  ))
}

function mockSystemTheme(initialDark: boolean) {
  let isDark = initialDark
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const mediaQuery = {
    get matches() {
      return isDark
    },
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener)
    },
    removeEventListener: (
      _type: string,
      listener: (event: MediaQueryListEvent) => void,
    ) => {
      listeners.delete(listener)
    },
  } as unknown as MediaQueryList

  vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery))

  return {
    setDark(nextValue: boolean) {
      isDark = nextValue
      const event = { matches: nextValue } as MediaQueryListEvent
      for (const listener of listeners) listener(event)
    },
  }
}
