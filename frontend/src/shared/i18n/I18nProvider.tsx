import {
  createContext,
  createEffect,
  createSignal,
  type Accessor,
  type ParentProps,
  useContext,
} from 'solid-js'

import {
  changeLocale,
  getActiveLocale,
  getLocaleMetadata,
  translate,
} from '@/shared/i18n/config'
import {
  formatDateTime as formatDateTimeValue,
  formatNumber as formatNumberValue,
} from '@/shared/i18n/formatters'
import type {
  Locale,
  TranslationKey,
  TranslationOptions,
} from '@/shared/i18n/types'

interface I18nContextValue {
  locale: Accessor<Locale>
  setLocale: (locale: Locale) => Promise<void>
  t: (key: TranslationKey, options?: TranslationOptions) => string
  formatDateTime: (
    value: Date | number,
    options: Intl.DateTimeFormatOptions,
  ) => string
  formatNumber: (value: number, options?: Intl.NumberFormatOptions) => string
}

const I18nContext = createContext<I18nContextValue>()

export function I18nProvider(props: ParentProps) {
  const [locale, setLocaleSignal] = createSignal(getActiveLocale())

  const setLocale = async (nextLocale: Locale) => {
    await changeLocale(nextLocale)
    if (nextLocale !== locale()) {
      setLocaleSignal(nextLocale)
    }
  }

  const t = (key: TranslationKey, options?: TranslationOptions) => {
    locale()
    return translate(key, options)
  }

  const formatDateTime = (
    value: Date | number,
    options: Intl.DateTimeFormatOptions,
  ) => formatDateTimeValue(locale(), value, options)

  const formatNumber = (
    value: number,
    options?: Intl.NumberFormatOptions,
  ) => formatNumberValue(locale(), value, options)

  createEffect(() => {
    const metadata = getLocaleMetadata(locale())
    document.documentElement.lang = metadata.code
    document.documentElement.dir = metadata.direction
  })

  return (
    <I18nContext.Provider
      value={{ locale, setLocale, t, formatDateTime, formatNumber }}
    >
      {props.children}
    </I18nContext.Provider>
  )
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext)
  if (context === undefined) {
    throw new Error('useI18n must be used within I18nProvider')
  }
  return context
}
