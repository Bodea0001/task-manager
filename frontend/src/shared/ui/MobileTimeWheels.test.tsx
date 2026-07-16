import { fireEvent, render, screen, waitFor, within } from '@solidjs/testing-library'
import { createSignal } from 'solid-js'
import { describe, expect, it } from 'vitest'

import { MobileTimeWheels } from '@/shared/ui/MobileTimeWheels'

describe('mobile time wheels', () => {
  it('moves selection and focus with listbox keyboard controls', async () => {
    function TimeWheelFixture() {
      const [time, setTime] = createSignal({ hour: 8, minute: 30 })
      return (
        <MobileTimeWheels
          hour={time().hour}
          hourLabel="Hours"
          minute={time().minute}
          minuteLabel="Minutes"
          onChange={(hour, minute) => setTime({ hour, minute })}
        />
      )
    }

    render(() => <TimeWheelFixture />)
    const hours = screen.getByRole('listbox', { name: 'Hours' })
    const selectedHour = within(hours).getByRole('option', {
      name: '08',
      selected: true,
    })
    selectedHour.focus()
    await fireEvent.keyDown(selectedHour, { key: 'ArrowDown' })

    const nextHour = within(hours).getByRole('option', {
      name: '09',
      selected: true,
    })
    await waitFor(() => expect(nextHour).toHaveFocus())
    await fireEvent.keyDown(nextHour, { key: 'End' })
    await waitFor(() =>
      expect(
        within(hours).getByRole('option', { name: '23', selected: true }),
      ).toHaveFocus(),
    )
  })
})
