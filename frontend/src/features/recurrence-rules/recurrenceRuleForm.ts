import { createSignal, untrack, type Accessor, type Setter } from 'solid-js'

import type {
  CreateRecurrenceRuleInput,
  UpdateRecurrenceRuleInput,
} from '@/entities/recurrence/api'
import type {
  RecurrenceBusinessDayPolicy,
  RecurrenceFrequency,
  RecurrenceRule,
  Weekday,
} from '@/entities/recurrence/model'

export type RecurrenceEndMode = 'count' | 'date' | 'never'
export type MonthRuleMode = 'month_day' | 'ordinal_weekday'

export interface RecurrenceRuleForm {
  anchorDate: Accessor<string>
  anchorDateValid: Accessor<boolean>
  businessDayPolicy: Accessor<RecurrenceBusinessDayPolicy>
  defaultTime: Accessor<string>
  defaultTimeValid: Accessor<boolean>
  durationHours: Accessor<string>
  durationMinutes: Accessor<string>
  endMode: Accessor<RecurrenceEndMode>
  frequency: Accessor<RecurrenceFrequency>
  hasDuration: Accessor<boolean>
  interval: Accessor<string>
  monthDay: Accessor<string>
  monthRuleMode: Accessor<MonthRuleMode>
  occurrencesLimit: Accessor<string>
  ordinalWeek: Accessor<string>
  ordinalWeekday: Accessor<Weekday>
  repeatUntil: Accessor<string>
  repeatUntilValid: Accessor<boolean>
  setAnchorDate: Setter<string>
  setAnchorDateValid: Setter<boolean>
  setBusinessDayPolicy: Setter<RecurrenceBusinessDayPolicy>
  setDefaultTime: Setter<string>
  setDefaultTimeValid: Setter<boolean>
  setDurationHours: Setter<string>
  setDurationMinutes: Setter<string>
  setEndMode: Setter<RecurrenceEndMode>
  setFrequency: Setter<RecurrenceFrequency>
  setHasDuration: Setter<boolean>
  setInterval: Setter<string>
  setMonthDay: Setter<string>
  setMonthRuleMode: Setter<MonthRuleMode>
  setOccurrencesLimit: Setter<string>
  setOrdinalWeek: Setter<string>
  setOrdinalWeekday: Setter<Weekday>
  setRepeatUntil: Setter<string>
  setRepeatUntilValid: Setter<boolean>
  setWeekdays: Setter<readonly Weekday[]>
  weekdays: Accessor<readonly Weekday[]>
  buildCreateInput: () => CreateRecurrenceRuleInput
  buildUpdateInput: () => UpdateRecurrenceRuleInput
  isDirty: () => boolean
  isValid: () => boolean
}

export function createRecurrenceRuleForm(rule?: RecurrenceRule): RecurrenceRuleForm {
  const initial = initialRuleValues(rule)
  const [frequency, setFrequency] = createSignal(initial.frequency)
  const [interval, setInterval] = createSignal(initial.interval)
  const [anchorDate, setAnchorDate] = createSignal(initial.anchorDate)
  const [anchorDateValid, setAnchorDateValid] = createSignal(true)
  const [defaultTime, setDefaultTime] = createSignal(initial.defaultTime)
  const [defaultTimeValid, setDefaultTimeValid] = createSignal(true)
  const [hasDuration, setHasDuration] = createSignal(initial.hasDuration)
  const [durationHours, setDurationHours] = createSignal(initial.durationHours)
  const [durationMinutes, setDurationMinutes] = createSignal(initial.durationMinutes)
  const [weekdays, setWeekdays] = createSignal<readonly Weekday[]>(initial.weekdays)
  const [monthRuleMode, setMonthRuleMode] = createSignal(initial.monthRuleMode)
  const [monthDay, setMonthDay] = createSignal(initial.monthDay)
  const [ordinalWeek, setOrdinalWeek] = createSignal(initial.ordinalWeek)
  const [ordinalWeekday, setOrdinalWeekday] = createSignal<Weekday>(
    initial.ordinalWeekday,
  )
  const [businessDayPolicy, setBusinessDayPolicy] =
    createSignal<RecurrenceBusinessDayPolicy>(initial.businessDayPolicy)
  const [endMode, setEndMode] = createSignal(initial.endMode)
  const [repeatUntil, setRepeatUntil] = createSignal(initial.repeatUntil)
  const [repeatUntilValid, setRepeatUntilValid] = createSignal(true)
  const [occurrencesLimit, setOccurrencesLimit] = createSignal(
    initial.occurrencesLimit,
  )

  const buildTimingInput = () => ({
    anchor_date: anchorDate(),
    default_time: defaultTime(),
    default_duration: hasDuration() ? durationToIso8601() : null,
    ...(endMode() === 'date'
      ? { repeat_until: repeatUntil() }
      : endMode() === 'count'
        ? { occurrences_limit: Number(occurrencesLimit()) }
        : {}),
  })

  const durationToIso8601 = () => {
    const hours = Number(durationHours())
    const minutes = Number(durationMinutes())
    return `PT${hours > 0 ? `${hours}H` : ''}${minutes > 0 ? `${minutes}M` : ''}`
  }

  const buildCreateInput = (): CreateRecurrenceRuleInput => ({
    frequency: frequency(),
    interval: Number(interval()),
    ...buildTimingInput(),
    weekdays: frequency() === 'weekly' ? weekdays() : [],
    month_rule:
      frequency() === 'monthly'
        ? {
            month_day:
              monthRuleMode() === 'month_day' ? Number(monthDay()) : null,
            week_of_month:
              monthRuleMode() === 'ordinal_weekday'
                ? asOrdinalWeek(ordinalWeek())
                : null,
            weekday:
              monthRuleMode() === 'ordinal_weekday' ? ordinalWeekday() : null,
            business_day_policy: businessDayPolicy(),
          }
        : null,
  })
  const initialValue = untrack(() =>
    JSON.stringify(
      rule === undefined ? buildCreateInput() : buildTimingInput(),
    ),
  )
  const isDirty = () =>
    JSON.stringify(
      rule === undefined ? buildCreateInput() : buildTimingInput(),
    ) !== initialValue

  const isValid = () => {
    const intervalValue = Number(interval())
    const occurrenceCount = Number(occurrencesLimit())
    const durationHourValue = Number(durationHours())
    const durationMinuteValue = Number(durationMinutes())
    const monthDayValue = Number(monthDay())
    const ordinalWeekValue = Number(ordinalWeek())
    return (
      Number.isInteger(intervalValue) &&
      intervalValue >= 1 &&
      anchorDate().length > 0 &&
      anchorDateValid() &&
      defaultTime().length > 0 &&
      defaultTimeValid() &&
      (!hasDuration() ||
        (Number.isInteger(durationHourValue) &&
          durationHourValue >= 0 &&
          Number.isInteger(durationMinuteValue) &&
          durationMinuteValue >= 0 &&
          durationMinuteValue <= 59 &&
          durationHourValue * 60 + durationMinuteValue > 0)) &&
      (frequency() !== 'weekly' || weekdays().length > 0) &&
      (frequency() !== 'monthly' ||
        (monthRuleMode() === 'month_day'
          ? Number.isInteger(monthDayValue) && monthDayValue >= 1 && monthDayValue <= 31
          : [-1, 1, 2, 3, 4, 5].includes(ordinalWeekValue))) &&
      (endMode() !== 'date' ||
        (repeatUntil().length > 0 &&
          repeatUntilValid() &&
          repeatUntil() >= anchorDate())) &&
      (endMode() !== 'count' ||
        (Number.isInteger(occurrenceCount) && occurrenceCount >= 1))
    )
  }

  return {
    anchorDate,
    anchorDateValid,
    businessDayPolicy,
    defaultTime,
    defaultTimeValid,
    durationHours,
    durationMinutes,
    endMode,
    frequency,
    hasDuration,
    interval,
    monthDay,
    monthRuleMode,
    occurrencesLimit,
    ordinalWeek,
    ordinalWeekday,
    repeatUntil,
    repeatUntilValid,
    setAnchorDate,
    setAnchorDateValid,
    setBusinessDayPolicy,
    setDefaultTime,
    setDefaultTimeValid,
    setDurationHours,
    setDurationMinutes,
    setEndMode,
    setFrequency,
    setHasDuration,
    setInterval,
    setMonthDay,
    setMonthRuleMode,
    setOccurrencesLimit,
    setOrdinalWeek,
    setOrdinalWeekday,
    setRepeatUntil,
    setRepeatUntilValid,
    setWeekdays,
    weekdays,
    buildCreateInput,
    buildUpdateInput: buildTimingInput,
    isDirty,
    isValid,
  }
}

function initialRuleValues(rule?: RecurrenceRule) {
  const now = new Date()
  now.setMinutes(0, 0, 0)
  now.setHours(now.getHours() + 1)
  const anchorDate = rule?.anchor_date ?? localDate(now)
  const duration = parseDuration(rule?.default_duration)
  const monthRuleMode: MonthRuleMode =
    rule === undefined ||
    (rule.month_rule?.month_day !== null &&
      rule.month_rule?.month_day !== undefined)
      ? 'month_day'
      : 'ordinal_weekday'
  return {
    anchorDate,
    businessDayPolicy: rule?.month_rule?.business_day_policy ?? 'none',
    defaultTime: rule?.default_time.slice(0, 5) ?? localTime(now),
    durationHours: String(Math.floor(duration / 60)),
    durationMinutes: String(duration % 60),
    endMode: rule?.repeat_until
      ? ('date' as const)
      : rule?.occurrences_limit
        ? ('count' as const)
        : ('never' as const),
    frequency: rule?.frequency ?? ('daily' as const),
    hasDuration: rule?.default_duration !== null && rule?.default_duration !== undefined,
    interval: String(rule?.interval ?? 1),
    monthDay: String(rule?.month_rule?.month_day ?? new Date(`${anchorDate}T00:00`).getDate()),
    monthRuleMode,
    occurrencesLimit: String(rule?.occurrences_limit ?? 1),
    ordinalWeek: String(rule?.month_rule?.week_of_month ?? 1),
    ordinalWeekday: rule?.month_rule?.weekday ?? weekdayFromDate(anchorDate),
    repeatUntil: rule?.repeat_until ?? addDays(anchorDate, 7),
    weekdays:
      rule?.weekdays.length ? rule.weekdays : [weekdayFromDate(anchorDate)],
  }
}

function parseDuration(value: string | null | undefined): number {
  if (!value) return 60
  const match = value.match(/^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$/)
  if (match === null) return 60
  return Number(match[1] ?? 0) * 24 * 60 + Number(match[2] ?? 0) * 60 + Number(match[3] ?? 0)
}

function asOrdinalWeek(value: string): -1 | 1 | 2 | 3 | 4 | 5 {
  return Number(value) as -1 | 1 | 2 | 3 | 4 | 5
}

function weekdayFromDate(value: string): Weekday {
  const day = new Date(`${value}T00:00`).getDay()
  return (day === 0 ? 7 : day) as Weekday
}

function addDays(value: string, days: number): string {
  const date = new Date(`${value}T00:00`)
  date.setDate(date.getDate() + days)
  return localDate(date)
}

function localDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function localTime(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}
