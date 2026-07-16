import { render, screen, waitFor } from '@solidjs/testing-library'
import { afterEach, describe, expect, it } from 'vitest'

import {
  OnlineStatusProvider,
  useOnlineStatus,
} from '@/shared/network/OnlineStatusProvider'

afterEach(() => window.dispatchEvent(new Event('online')))

describe('online status', () => {
  it('notifies the interface when connectivity changes', async () => {
    render(() => (
      <OnlineStatusProvider>
        <OnlineStatusProbe />
      </OnlineStatusProvider>
    ))

    expect(screen.getByText('online')).toBeInTheDocument()

    window.dispatchEvent(new Event('offline'))
    await waitFor(() => expect(screen.getByText('offline')).toBeInTheDocument())

    window.dispatchEvent(new Event('online'))
    await waitFor(() => expect(screen.getByText('online')).toBeInTheDocument())
  })
})

function OnlineStatusProbe() {
  const { isOnline } = useOnlineStatus()
  return <span>{isOnline() ? 'online' : 'offline'}</span>
}
