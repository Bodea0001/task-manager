import flatpickr from 'flatpickr'
import { Russian } from 'flatpickr/dist/l10n/ru.js'
import type { CustomLocale } from 'flatpickr/dist/types/locale'

import type { Locale } from '@/shared/i18n/types'

type DatePart = 'day' | 'month'

export interface DateTimeLocaleConfig {
  calendarLocale: CustomLocale
  dateFormat: string
  dateMask: string
  dateParts: readonly [DatePart, DatePart]
  datePlaceholder: string
  dateSeparator: string
  mask: string
  placeholder: string
  timeMask: string
  timePlaceholder: string
}

const dateTimeLocales = {
  en: {
    calendarLocale: flatpickr.l10ns.default,
    dateFormat: 'm/d/Y',
    dateMask: 'M/D/Y',
    dateParts: ['month', 'day'],
    datePlaceholder: 'MM/DD/YYYY',
    dateSeparator: '/',
    mask: 'M/D/Y H:m',
    placeholder: 'MM/DD/YYYY HH:MM',
    timeMask: 'H:m',
    timePlaceholder: 'HH:MM',
  },
  ru: {
    calendarLocale: Russian,
    dateFormat: 'd.m.Y',
    dateMask: 'D.M.Y',
    dateParts: ['day', 'month'],
    datePlaceholder: 'ДД.ММ.ГГГГ',
    dateSeparator: '.',
    mask: 'D.M.Y H:m',
    placeholder: 'ДД.ММ.ГГГГ ЧЧ:ММ',
    timeMask: 'H:m',
    timePlaceholder: 'ЧЧ:ММ',
  },
} as const satisfies Record<Locale, DateTimeLocaleConfig>

export function getDateTimeLocaleConfig(
  locale: Locale,
): DateTimeLocaleConfig {
  return dateTimeLocales[locale]
}
