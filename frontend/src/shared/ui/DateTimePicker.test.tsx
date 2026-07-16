import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@solidjs/testing-library'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { changeLocale } from '@/shared/i18n/config'
import { I18nProvider } from '@/shared/i18n/I18nProvider'
import { DateTimePicker } from '@/shared/ui/DateTimePicker'

afterEach(async () => {
  await changeLocale('en')
})

describe('Date and time input', () => {
  it('uses a localized masked value and preserves incomplete input for correction', async () => {
    const onChange = vi.fn()
    const onValidityChange = vi.fn()

    render(() => (
      <I18nProvider>
        <DateTimePicker
          label="Deadline"
          name="deadline"
          value="2026-07-15T13:30"
          required
          onChange={onChange}
          onValidityChange={onValidityChange}
        />
      </I18nProvider>
    ))

    const input = screen.getByRole('textbox', { name: 'Deadline' })
    expect(input).toHaveValue('07/15/2026 13:30')

    await fireEvent.input(input, { target: { value: 'not a date' } })
    expect(input).not.toHaveValue('not a date')

    await fireEvent.input(input, { target: { value: '07/1' } })
    await fireEvent.blur(input)
    expect(input).toHaveValue('07/1')
    expect(onValidityChange).toHaveBeenLastCalledWith(false)

    await fireEvent.input(input, { target: { value: '07/16/2026 14:35' } })
    expect(onValidityChange).toHaveBeenLastCalledWith(true)
    expect(onChange).toHaveBeenLastCalledWith('2026-07-16T14:35')
  })

  it('allows navigating directly to another month', async () => {
    render(() => (
      <I18nProvider>
        <DateTimePicker
          label="Deadline"
          name="deadline"
          value="2026-07-15T13:30"
          onChange={() => undefined}
        />
      </I18nProvider>
    ))

    const month = screen.getByRole('button', { name: 'Month July' })
    await fireEvent.keyDown(month, { key: 'ArrowDown' })
    await fireEvent.click(
      await screen.findByRole('option', { name: 'August' }),
    )

    expect(screen.getByRole('button', { name: 'Month August' })).toBeVisible()
  })

  it('closes the calendar when focus leaves the date field', async () => {
    render(() => (
      <I18nProvider>
        <DateTimePicker
          label="Deadline"
          name="deadline"
          value="2026-07-15T13:30"
          onChange={() => undefined}
        />
        <button type="button">Next field</button>
      </I18nProvider>
    ))

    const input = screen.getByRole('textbox', { name: 'Deadline' })
    const calendar = document.querySelector('.flatpickr-calendar')
    input.focus()
    expect(calendar).toHaveClass('open')

    screen.getByRole('button', { name: 'Next field' }).focus()
    await waitFor(() => expect(calendar).not.toHaveClass('open'))
  })

  it('uses the Russian numeric format without punctuation between date and time', async () => {
    await changeLocale('ru')

    render(() => (
      <I18nProvider>
        <DateTimePicker
          label="Дедлайн"
          name="deadline"
          value="2026-07-15T13:30"
          onChange={() => undefined}
        />
      </I18nProvider>
    ))

    expect(screen.getByRole('textbox', { name: 'Дедлайн' })).toHaveValue(
      '15.07.2026 13:30',
    )
  })

  it('emits API date and time values when those fields are edited separately', async () => {
    const onDateChange = vi.fn()
    const onTimeChange = vi.fn()

    render(() => (
      <I18nProvider>
        <DateTimePicker
          mode="date"
          label="First occurrence date"
          name="anchor_date"
          value="2026-07-15"
          onChange={onDateChange}
        />
        <DateTimePicker
          mode="time"
          label="Deadline time"
          name="default_time"
          value="13:30"
          onChange={onTimeChange}
        />
      </I18nProvider>
    ))

    const dateInput = screen.getByRole('textbox', {
      name: 'First occurrence date',
    })
    const timeInput = screen.getByRole('textbox', { name: 'Deadline time' })
    expect(dateInput).toHaveValue('07/15/2026')
    expect(timeInput).toHaveValue('13:30')

    await fireEvent.input(dateInput, { target: { value: '07/20/2026' } })
    await fireEvent.input(timeInput, { target: { value: '08:45' } })

    expect(onDateChange).toHaveBeenLastCalledWith('2026-07-20')
    expect(onTimeChange).toHaveBeenLastCalledWith('08:45')
  })

  it('allows selecting hours and minutes with the mobile time wheels', async () => {
    const onChange = vi.fn()

    render(() => (
      <I18nProvider>
        <DateTimePicker
          label="Deadline"
          name="deadline"
          value="2026-07-15T13:30"
          onChange={onChange}
        />
      </I18nProvider>
    ))

    const hours = screen.getByRole('listbox', {
      name: 'Hours',
      hidden: true,
    })
    const minutes = screen.getByRole('listbox', {
      name: 'Minutes',
      hidden: true,
    })
    await fireEvent.click(
      within(hours).getByRole('option', { name: '14', hidden: true }),
    )
    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith('2026-07-15T14:30'),
    )
    await fireEvent.click(
      within(minutes).getByRole('option', { name: '45', hidden: true }),
    )

    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith('2026-07-15T14:45'),
    )
  })

  it('rejects out-of-range values in the calendar time inputs', async () => {
    render(() => (
      <I18nProvider>
        <DateTimePicker
          label="Deadline"
          name="deadline"
          value="2026-07-15T13:30"
          onChange={() => undefined}
        />
      </I18nProvider>
    ))

    const hourInput = document.querySelector<HTMLInputElement>('.flatpickr-hour')
    const minuteInput = document.querySelector<HTMLInputElement>(
      '.flatpickr-minute',
    )
    expect(hourInput).not.toBeNull()
    expect(minuteInput).not.toBeNull()

    await fireEvent.input(hourInput!, { target: { value: '24' } })
    await fireEvent.input(minuteInput!, { target: { value: '60' } })

    expect(hourInput).toHaveValue(13)
    expect(minuteInput).toHaveValue(30)
  })
})
