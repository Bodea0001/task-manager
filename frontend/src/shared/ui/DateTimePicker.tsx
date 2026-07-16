import flatpickr from 'flatpickr'
import IMask, { MaskedRange, type InputMask } from 'imask'
import CalendarDays from 'lucide-solid/icons/calendar-days'
import Clock3 from 'lucide-solid/icons/clock-3'
import { createEffect, createSignal, onCleanup, onMount, Show, untrack } from 'solid-js'
import { render } from 'solid-js/web'

import 'flatpickr/dist/flatpickr.css'
import './date-time-picker.css'

import { useI18n } from '@/shared/i18n/I18nProvider'
import type { Locale } from '@/shared/i18n/types'
import {
  getDateTimeLocaleConfig,
  type DateTimeLocaleConfig,
} from '@/shared/ui/date-time-locales'
import { MobileTimeWheels } from '@/shared/ui/MobileTimeWheels'
import { SelectField, type SelectOption } from '@/shared/ui/SelectField'

type DateTimeMaskOptions = ReturnType<typeof getDateTimeMaskOptions>
type DateTimePickerMode = 'date' | 'datetime' | 'time'

interface MobileTimeWheelsController {
  dispose: () => void
  sync: () => void
}

export function DateTimePicker(props: {
  disabled?: boolean
  error?: string
  label: string
  mode?: DateTimePickerMode
  name: string
  onChange: (value: string) => void
  onValidityChange?: (valid: boolean) => void
  required?: boolean
  value: string
}) {
  const { locale, t } = useI18n()
  const mode = () => props.mode ?? 'datetime'
  let input!: HTMLInputElement
  let picker: flatpickr.Instance | undefined
  let inputMask: InputMask<DateTimeMaskOptions> | undefined
  let maskedInput: HTMLInputElement | undefined
  let blurCloseTimeout: ReturnType<typeof setTimeout> | undefined
  let calendarInteraction = false
  let calendarInteractionTimeout: ReturnType<typeof setTimeout> | undefined
  let removeCalendarActions: (() => void) | undefined
  let removeMonthSelector: (() => void) | undefined
  let removeTimeInputLimits: (() => void) | undefined
  let mobileTimeWheels: MobileTimeWheelsController | undefined
  let syncingMask = false
  const [currentMonth, setCurrentMonth] = createSignal(0)
  const errorId = () => `date-time-${props.name.replaceAll('_', '-')}-error`

  const syncAccessibility = (instance: flatpickr.Instance) => {
    for (const element of [instance.input, instance.altInput, instance.mobileInput]) {
      if (element === undefined) continue
      if (props.error === undefined) {
        element.removeAttribute('aria-invalid')
        element.removeAttribute('aria-describedby')
      } else {
        element.setAttribute('aria-invalid', 'true')
        element.setAttribute('aria-describedby', errorId())
      }
    }
  }

  const syncInputMask = (instance: flatpickr.Instance) => {
    if (inputMask === undefined || instance.altInput === undefined) {
      return
    }
    syncingMask = true
    inputMask.updateValue()
    syncingMask = false
  }

  const handleMaskedInput = () => {
    if (syncingMask || inputMask === undefined || picker === undefined) {
      return
    }
    const date = inputMask.masked.isComplete
      ? parseDisplayValue(
          inputMask.value,
          getDateTimeLocaleConfig(locale()),
          mode(),
        )
      : undefined
    props.onValidityChange?.(date !== undefined)
    if (date !== undefined) {
      picker.setDate(date, true)
    }
  }

  const handleMaskedInputBlur = (event: FocusEvent) => {
    if (inputMask !== undefined && !inputMask.masked.isComplete) {
      event.stopImmediatePropagation()
    }
    clearTimeout(blurCloseTimeout)
    blurCloseTimeout = setTimeout(() => {
      const activeElement = document.activeElement
      if (
        picker?.isOpen &&
        !calendarInteraction &&
        !picker.calendarContainer.contains(activeElement)
      ) {
        picker.close()
      }
    })
  }

  const beginCalendarInteraction = () => {
    clearTimeout(calendarInteractionTimeout)
    calendarInteraction = true
  }

  const endCalendarInteraction = () => {
    clearTimeout(calendarInteractionTimeout)
    calendarInteractionTimeout = setTimeout(() => {
      calendarInteraction = false
    })
  }

  onMount(() => {
    const initial = untrack(() => ({
      disabled: props.disabled,
      label: props.label,
      locale: locale(),
      mode: mode(),
      value: props.value,
    }))
    const initialLocaleConfig = getDateTimeLocaleConfig(initial.locale)
    picker = flatpickr(input, {
      allowInput: true,
      altFormat: getDisplayFormat(initialLocaleConfig, initial.mode),
      altInput: true,
      dateFormat: getValueFormat(initial.mode),
      defaultDate: initial.value || undefined,
      disableMobile: true,
      enableTime: initial.mode !== 'date',
      locale: initialLocaleConfig.calendarLocale,
      minuteIncrement: 5,
      monthSelectorType: 'static',
      noCalendar: initial.mode === 'time',
      time_24hr: true,
      onChange: (_dates, value, instance) => {
        syncInputMask(instance)
        props.onValidityChange?.(value.length > 0 || props.required !== true)
        props.onChange(value)
      },
      onMonthChange: (_dates, _value, instance) => {
        setCurrentMonth(instance.currentMonth)
      },
      onOpen: () => mobileTimeWheels?.sync(),
      onReady: (_dates, _value, instance) => {
        instance.altInput?.setAttribute('aria-label', initial.label)
        instance.mobileInput?.setAttribute('aria-label', initial.label)
        syncAccessibility(instance)
        instance.calendarContainer.addEventListener(
          'pointerdown',
          beginCalendarInteraction,
        )
        instance.calendarContainer.addEventListener(
          'pointerup',
          endCalendarInteraction,
        )
        instance.calendarContainer.addEventListener(
          'pointercancel',
          endCalendarInteraction,
        )
        setCurrentMonth(instance.currentMonth)
        removeCalendarActions = mountCalendarActions(
          instance,
          () => t('common.dateTime.done'),
        )
        if (initial.mode !== 'date') {
          removeTimeInputLimits = constrainFlatpickrTimeInputs(instance)
          mobileTimeWheels = mountMobileTimeWheels(
            instance,
            () => t('common.dateTime.hours'),
            () => t('common.dateTime.minutes'),
          )
        }
        if (initial.mode !== 'time') {
          removeMonthSelector = mountMonthSelector(
            instance,
            // `render` in mountMonthSelector tracks this accessor in its own root.
            // eslint-disable-next-line solid/reactivity
            () => currentMonth().toString(),
            () => getMonthOptions(locale()),
            (month) => instance.changeMonth(Number(month), false),
            () => t('common.dateTime.month'),
          )
        }
        if (instance.altInput !== undefined) {
          maskedInput = instance.altInput
          maskedInput.placeholder = getPlaceholder(
            initialLocaleConfig,
            initial.mode,
          )
          inputMask = IMask(
            maskedInput,
            getDateTimeMaskOptions(initialLocaleConfig, initial.mode),
          )
          inputMask.on('accept', handleMaskedInput)
          maskedInput.addEventListener('blur', handleMaskedInputBlur, true)
          props.onValidityChange?.(
            initial.value.length > 0 || props.required !== true,
          )
        }
      },
    })
    setDisabled(picker, initial.disabled === true)
  })

  createEffect(() => {
    const nextLocale = locale()
    const nextValue = props.value
    const disabled = props.disabled === true
    const label = props.label
    const nextMode = mode()
    if (picker === undefined) {
      return
    }
    const nextLocaleConfig = getDateTimeLocaleConfig(nextLocale)

    picker.set({
      altFormat: getDisplayFormat(nextLocaleConfig, nextMode),
      locale: nextLocaleConfig.calendarLocale,
    })
    if (picker.input.value !== nextValue) {
      picker.setDate(nextValue, false, getValueFormat(nextMode))
    } else if (picker.selectedDates[0] !== undefined) {
      picker.setDate(picker.selectedDates[0], false)
    }
    picker.altInput?.setAttribute('aria-label', label)
    picker.mobileInput?.setAttribute('aria-label', label)
    syncAccessibility(picker)
    if (picker.altInput !== undefined && inputMask !== undefined) {
      picker.altInput.placeholder = getPlaceholder(nextLocaleConfig, nextMode)
      inputMask.updateOptions(getDateTimeMaskOptions(nextLocaleConfig, nextMode))
      syncInputMask(picker)
    }
    setDisabled(picker, disabled)
    mobileTimeWheels?.sync()
  })

  onCleanup(() => {
    clearTimeout(blurCloseTimeout)
    clearTimeout(calendarInteractionTimeout)
    if (maskedInput !== undefined) {
      maskedInput.removeEventListener('blur', handleMaskedInputBlur, true)
    }
    if (picker !== undefined) {
      picker.calendarContainer.removeEventListener(
        'pointerdown',
        beginCalendarInteraction,
      )
      picker.calendarContainer.removeEventListener(
        'pointerup',
        endCalendarInteraction,
      )
      picker.calendarContainer.removeEventListener(
        'pointercancel',
        endCalendarInteraction,
      )
    }
    inputMask?.destroy()
    mobileTimeWheels?.dispose()
    removeTimeInputLimits?.()
    removeCalendarActions?.()
    removeMonthSelector?.()
    picker?.destroy()
  })

  return (
    <label class="date-time-field">
      <span>{props.label}</span>
      <span class="date-time-control">
        <Show
          when={mode() === 'time'}
          fallback={<CalendarDays size={16} strokeWidth={1.8} aria-hidden="true" />}
        >
          <Clock3 size={16} strokeWidth={1.8} aria-hidden="true" />
        </Show>
        <input
          ref={input}
          class="date-time-input"
          name={props.name}
          type="text"
          value={props.value}
          autocomplete="off"
          required={props.required}
          disabled={props.disabled}
          aria-invalid={props.error === undefined ? undefined : 'true'}
          aria-describedby={props.error === undefined ? undefined : errorId()}
        />
      </span>
      <Show when={props.error}>
        {(error) => (
          <small id={errorId()} class="date-time-field-error">
            {error()}
          </small>
        )}
      </Show>
    </label>
  )
}

function getDisplayFormat(
  config: DateTimeLocaleConfig,
  mode: DateTimePickerMode,
): string {
  if (mode === 'date') return config.dateFormat
  if (mode === 'time') return 'H:i'
  return `${config.dateFormat} H:i`
}

function getDateTimeMaskOptions(
  config: DateTimeLocaleConfig,
  mode: DateTimePickerMode,
) {
  return {
    mask:
      mode === 'date'
        ? config.dateMask
        : mode === 'time'
          ? config.timeMask
          : config.mask,
    lazy: true,
    overwrite: true,
    skipInvalid: true,
    blocks: {
      D: { mask: MaskedRange, from: 1, to: 31, maxLength: 2, autofix: 'pad' },
      M: { mask: MaskedRange, from: 1, to: 12, maxLength: 2, autofix: 'pad' },
      Y: { mask: MaskedRange, from: 1900, to: 9999, maxLength: 4 },
      H: { mask: MaskedRange, from: 0, to: 23, maxLength: 2, autofix: 'pad' },
      m: { mask: MaskedRange, from: 0, to: 59, maxLength: 2, autofix: 'pad' },
    },
  } as const
}

function parseDisplayValue(
  value: string,
  locale: DateTimeLocaleConfig,
  mode: DateTimePickerMode,
): Date | undefined {
  if (mode === 'time') {
    const match = value.match(/^(\d{2}):(\d{2})$/)
    if (match === null) return undefined
    const hour = Number(match[1])
    const minute = Number(match[2])
    return hour <= 23 && minute <= 59
      ? new Date(2000, 0, 1, hour, minute)
      : undefined
  }
  const separator = escapeRegularExpression(locale.dateSeparator)
  const timePattern = mode === 'datetime' ? ' (\\d{2}):(\\d{2})' : ''
  const match = value.match(
    new RegExp(`^(\\d{2})${separator}(\\d{2})${separator}(\\d{4})${timePattern}$`),
  )
  if (match === null) {
    return undefined
  }
  const [, first, second, yearValue, hourValue = '0', minuteValue = '0'] = match
  const dateParts = { day: 0, month: 0 }
  dateParts[locale.dateParts[0]] = Number(first)
  dateParts[locale.dateParts[1]] = Number(second)
  const { day, month } = dateParts
  const year = Number(yearValue)
  const hour = Number(hourValue)
  const minute = Number(minuteValue)
  const date = new Date(year, month - 1, day, hour, minute)
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day ||
    date.getHours() !== hour ||
    date.getMinutes() !== minute
  ) {
    return undefined
  }
  return date
}

function getValueFormat(mode: DateTimePickerMode): string {
  if (mode === 'date') return 'Y-m-d'
  if (mode === 'time') return 'H:i'
  return 'Y-m-d\\TH:i'
}

function getPlaceholder(
  config: DateTimeLocaleConfig,
  mode: DateTimePickerMode,
): string {
  if (mode === 'date') return config.datePlaceholder
  if (mode === 'time') return config.timePlaceholder
  return config.placeholder
}

function escapeRegularExpression(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function getMonthOptions(locale: Locale): SelectOption[] {
  const formatter = new Intl.DateTimeFormat(locale, { month: 'long' })
  return Array.from({ length: 12 }, (_, month) => ({
    label: formatter.format(new Date(2020, month, 1)),
    value: month.toString(),
  }))
}

function mountMonthSelector(
  instance: flatpickr.Instance,
  value: () => string,
  options: () => SelectOption[],
  onChange: (month: string) => void,
  label: () => string,
): () => void {
  const nativeMonth = instance.monthNav.querySelector<HTMLElement>('.cur-month')
  if (nativeMonth === null) {
    return () => undefined
  }
  const host = document.createElement('div')
  host.className = 'flatpickr-month-select-host'
  nativeMonth.classList.add('flatpickr-native-month')
  nativeMonth.before(host)
  const dispose = render(
    () => (
      <SelectField
        compact
        label={label()}
        value={value()}
        options={options()}
        portalMount={instance.calendarContainer}
        onChange={onChange}
      />
    ),
    host,
  )
  return () => {
    dispose()
    host.remove()
  }
}

function mountCalendarActions(
  instance: flatpickr.Instance,
  doneLabel: () => string,
): () => void {
  const host = document.createElement('div')
  host.className = 'flatpickr-mobile-actions'
  instance.calendarContainer.append(host)
  const dispose = render(
    () => (
      <button type="button" onClick={() => instance.close()}>
        {doneLabel()}
      </button>
    ),
    host,
  )
  return () => {
    dispose()
    host.remove()
  }
}

function mountMobileTimeWheels(
  instance: flatpickr.Instance,
  hourLabel: () => string,
  minuteLabel: () => string,
): MobileTimeWheelsController {
  const [time, setTime] = createSignal(readFlatpickrTime(instance))
  const host = document.createElement('div')
  host.className = 'flatpickr-mobile-time-host'
  instance.timeContainer?.after(host)
  const dispose = render(
    () => (
      <MobileTimeWheels
        hour={time().hour}
        hourLabel={hourLabel()}
        minute={time().minute}
        minuteLabel={minuteLabel()}
        onChange={(hour, minute) => {
          applyFlatpickrTime(instance, hour, minute)
          setTime(readFlatpickrTime(instance))
        }}
      />
    ),
    host,
  )
  return {
    dispose: () => {
      dispose()
      host.remove()
    },
    sync: () => setTime(readFlatpickrTime(instance)),
  }
}

function readFlatpickrTime(instance: flatpickr.Instance): {
  hour: number
  minute: number
} {
  return {
    hour: Number(
      instance.hourElement?.value ??
        instance.latestSelectedDateObj?.getHours() ??
        0,
    ),
    minute: Number(
      instance.minuteElement?.value ??
        instance.latestSelectedDateObj?.getMinutes() ??
        0,
    ),
  }
}

function applyFlatpickrTime(
  instance: flatpickr.Instance,
  hour: number,
  minute: number,
): void {
  const selectedDate = instance.latestSelectedDateObj ?? instance.selectedDates[0]
  if (selectedDate !== undefined) {
    const nextDate = new Date(selectedDate)
    nextDate.setHours(hour, minute, 0, 0)
    instance.setDate(nextDate, true)
    return
  }
  if (instance.hourElement === undefined || instance.minuteElement === undefined) {
    return
  }
  instance.hourElement.value = hour.toString().padStart(2, '0')
  instance.minuteElement.value = minute.toString().padStart(2, '0')
  instance.hourElement.dispatchEvent(new FocusEvent('blur'))
}

function constrainFlatpickrTimeInputs(
  instance: flatpickr.Instance,
): () => void {
  const constraints = [
    { input: instance.hourElement, maximum: 23 },
    { input: instance.minuteElement, maximum: 59 },
  ]
  const cleanups = constraints.flatMap(({ input, maximum }) => {
    if (input === undefined) return []
    input.min = '0'
    input.max = maximum.toString()
    input.inputMode = 'numeric'
    let lastValidValue = input.value

    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        event.key.length !== 1 ||
        /^\d$/.test(event.key)
      ) {
        return
      }
      event.preventDefault()
    }
    const handleInput = () => {
      if (input.value === '') {
        lastValidValue = ''
        return
      }
      if (
        /^\d{1,2}$/.test(input.value) &&
        Number(input.value) <= maximum
      ) {
        lastValidValue = input.value
        return
      }
      input.value = lastValidValue
    }

    input.addEventListener('keydown', handleKeyDown, true)
    input.addEventListener('input', handleInput, true)
    return [
      () => {
        input.removeEventListener('keydown', handleKeyDown, true)
        input.removeEventListener('input', handleInput, true)
      },
    ]
  })
  return () => cleanups.forEach((cleanup) => cleanup())
}

function setDisabled(picker: flatpickr.Instance, disabled: boolean): void {
  picker.input.disabled = disabled
  if (picker.altInput !== undefined) {
    picker.altInput.disabled = disabled
  }
  if (picker.mobileInput !== undefined) {
    picker.mobileInput.disabled = disabled
  }
  picker.set('clickOpens', !disabled)
}
