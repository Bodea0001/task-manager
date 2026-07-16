import { createInstance } from 'i18next'

import { enTranslation } from '@/shared/i18n/locales/en'
import { ruTranslation } from '@/shared/i18n/locales/ru'
import type {
  Locale,
  LocaleMetadata,
  TranslationKey,
  TranslationOptions,
} from '@/shared/i18n/types'

const LOCALE_STORAGE_KEY = 'task-manager.locale'
export const fallbackLocale: Locale = 'en'

export const supportedLocales: readonly LocaleMetadata[] = [
  { code: 'en', direction: 'ltr', nativeName: 'English' },
  { code: 'ru', direction: 'ltr', nativeName: 'Русский' },
]

export const i18n = createInstance()

let initialization: Promise<void> | undefined

export function initializeI18n(): Promise<void> {
  initialization ??= i18n
    .init({
      defaultNS: 'translation',
      fallbackLng: fallbackLocale,
      interpolation: { escapeValue: false },
      lng: detectInitialLocale(),
      resources: {
        en: { translation: enTranslation },
        ru: { translation: ruTranslation },
      },
      returnNull: false,
      supportedLngs: supportedLocales.map((locale) => locale.code),
    })
    .then(() => {
      applyDocumentLocale(getActiveLocale())
    })

  return initialization
}

export function getActiveLocale(): Locale {
  return normalizeLocale(i18n.resolvedLanguage || i18n.language) || fallbackLocale
}

export async function changeLocale(locale: Locale): Promise<void> {
  persistLocale(locale)

  if (locale === getActiveLocale()) {
    return
  }

  await i18n.changeLanguage(locale)
  applyDocumentLocale(locale)
}

export function translate(
  key: TranslationKey,
  options?: TranslationOptions,
): string {
  return i18n.t(key, options) as string
}

export function getLocaleMetadata(locale: Locale): LocaleMetadata {
  return (
    supportedLocales.find((candidate) => candidate.code === locale) ||
    supportedLocales.find((candidate) => candidate.code === fallbackLocale)!
  )
}

function detectInitialLocale(): Locale {
  const storedLocale = readStoredLocale()
  if (storedLocale !== undefined) {
    return storedLocale
  }

  for (const language of navigator.languages || [navigator.language]) {
    const locale = normalizeLocale(language)
    if (locale !== undefined) {
      return locale
    }
  }

  return fallbackLocale
}

function normalizeLocale(value: string | undefined): Locale | undefined {
  const language = value?.toLowerCase().split('-')[0]
  return supportedLocales.find((locale) => locale.code === language)?.code
}

function readStoredLocale(): Locale | undefined {
  try {
    return normalizeLocale(localStorage.getItem(LOCALE_STORAGE_KEY) || undefined)
  } catch {
    return undefined
  }
}

function persistLocale(locale: Locale): void {
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    // The selected locale still applies to the current session.
  }
}

function applyDocumentLocale(locale: Locale): void {
  const metadata = getLocaleMetadata(locale)
  document.documentElement.lang = metadata.code
  document.documentElement.dir = metadata.direction
}
