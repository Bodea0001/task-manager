import { fireEvent, render, screen } from '@solidjs/testing-library'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageSettings } from '@/features/language-settings/LanguageSettings'
import {
  changeLocale,
  initializeI18n,
  translate,
} from '@/shared/i18n/config'
import { I18nProvider } from '@/shared/i18n/I18nProvider'

beforeEach(async () => {
  await initializeI18n()
  await changeLocale('en')
})

afterEach(async () => {
  vi.unstubAllGlobals()
  await changeLocale('en')
})

describe('internationalization', () => {
  it('switches the rendered interface and document language', async () => {
    render(() => (
      <I18nProvider>
        <LanguageSettings />
      </I18nProvider>
    ))

    await fireEvent.click(screen.getByRole('button', { name: 'Russian' }))

    expect(
      await screen.findByRole('heading', { name: 'Язык' }),
    ).toBeVisible()
    expect(document.documentElement.lang).toBe('ru')
    expect(document.documentElement.dir).toBe('ltr')
  })

  it('uses Russian plural forms without requesting translation chunks', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await changeLocale('ru')

    expect(translate('tasks.itemCount', { count: 1 })).toBe('1 задача')
    expect(translate('tasks.itemCount', { count: 2 })).toBe('2 задачи')
    expect(translate('tasks.itemCount', { count: 5 })).toBe('5 задач')

    await changeLocale('en')
    await changeLocale('ru')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
