import type { Locale } from '@/shared/i18n/types'

const dateTimeFormatters = new Map<string, Intl.DateTimeFormat>()
const numberFormatters = new Map<string, Intl.NumberFormat>()

export function formatDateTime(
  locale: Locale,
  value: Date | number,
  options: Intl.DateTimeFormatOptions,
): string {
  const key = `${locale}:${JSON.stringify(options)}`
  let formatter = dateTimeFormatters.get(key)

  if (formatter === undefined) {
    formatter = new Intl.DateTimeFormat(locale, options)
    dateTimeFormatters.set(key, formatter)
  }

  return formatter.format(value)
}

export function formatNumber(
  locale: Locale,
  value: number,
  options: Intl.NumberFormatOptions = {},
): string {
  const key = `${locale}:${JSON.stringify(options)}`
  let formatter = numberFormatters.get(key)

  if (formatter === undefined) {
    formatter = new Intl.NumberFormat(locale, options)
    numberFormatters.set(key, formatter)
  }

  return formatter.format(value)
}
