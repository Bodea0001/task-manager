import { createEffect, For, onCleanup } from 'solid-js'

const ITEM_HEIGHT = 32
const SCROLL_SETTLE_DELAY_MS = 90

export function MobileTimeWheels(props: {
  hour: number
  hourLabel: string
  minute: number
  minuteLabel: string
  onChange: (hour: number, minute: number) => void
}) {
  let hourList!: HTMLDivElement
  let minuteList!: HTMLDivElement
  let hourScrollTimeout: ReturnType<typeof setTimeout> | undefined
  let minuteScrollTimeout: ReturnType<typeof setTimeout> | undefined
  const hours = Array.from({ length: 24 }, (_, value) => value)
  const minutes = Array.from({ length: 60 }, (_, value) => value)

  createEffect(() => {
    hourList.scrollTop = props.hour * ITEM_HEIGHT
  })
  createEffect(() => {
    minuteList.scrollTop = props.minute * ITEM_HEIGHT
  })

  const settleHour = () => {
    clearTimeout(hourScrollTimeout)
    hourScrollTimeout = setTimeout(() => {
      const hour = nearestValue(hourList.scrollTop, hours.length)
      if (hour !== props.hour) props.onChange(hour, props.minute)
    }, SCROLL_SETTLE_DELAY_MS)
  }

  const settleMinute = () => {
    clearTimeout(minuteScrollTimeout)
    minuteScrollTimeout = setTimeout(() => {
      const minute = nearestValue(minuteList.scrollTop, minutes.length)
      if (minute !== props.minute) props.onChange(props.hour, minute)
    }, SCROLL_SETTLE_DELAY_MS)
  }

  onCleanup(() => {
    clearTimeout(hourScrollTimeout)
    clearTimeout(minuteScrollTimeout)
  })

  return (
    <div class="flatpickr-mobile-time-wheels">
      <TimeWheel
        setRef={(element) => (hourList = element)}
        label={props.hourLabel}
        options={hours}
        value={props.hour}
        onChange={(hour) => props.onChange(hour, props.minute)}
        onScroll={settleHour}
      />
      <span class="flatpickr-mobile-time-separator" aria-hidden="true">
        :
      </span>
      <TimeWheel
        setRef={(element) => (minuteList = element)}
        label={props.minuteLabel}
        options={minutes}
        value={props.minute}
        onChange={(minute) => props.onChange(props.hour, minute)}
        onScroll={settleMinute}
      />
    </div>
  )
}

function TimeWheel(props: {
  label: string
  onChange: (value: number) => void
  onScroll: () => void
  options: readonly number[]
  setRef: (element: HTMLDivElement) => void
  value: number
}) {
  const selectValue = (value: number, listbox: HTMLElement) => {
    if (value !== props.value) props.onChange(value)
    queueMicrotask(() => {
      listbox
        .querySelector<HTMLElement>('[role="option"][aria-selected="true"]')
        ?.focus()
    })
  }

  return (
    <div
      ref={props.setRef}
      class="flatpickr-mobile-time-wheel"
      role="listbox"
      aria-label={props.label}
      onScroll={() => props.onScroll()}
      onKeyDown={(event) => {
        let nextValue: number | undefined
        if (event.key === 'ArrowDown') {
          nextValue = Math.min(props.options.length - 1, props.value + 1)
        }
        if (event.key === 'ArrowUp') nextValue = Math.max(0, props.value - 1)
        if (event.key === 'Home') nextValue = 0
        if (event.key === 'End') nextValue = props.options.length - 1
        if (nextValue === undefined) return
        event.preventDefault()
        selectValue(nextValue, event.currentTarget)
      }}
    >
      <For each={props.options}>
        {(option) => (
          <button
            type="button"
            role="option"
            aria-selected={option === props.value}
            tabIndex={option === props.value ? 0 : -1}
            onClick={() => props.onChange(option)}
          >
            {option.toString().padStart(2, '0')}
          </button>
        )}
      </For>
    </div>
  )
}

function nearestValue(scrollTop: number, optionCount: number): number {
  return Math.max(
    0,
    Math.min(optionCount - 1, Math.round(scrollTop / ITEM_HEIGHT)),
  )
}
