import { afterEach, describe, expect, it, vi } from 'vitest'

import { logout } from '@/features/auth/api'
import {
  clearAuthSession,
  hasAuthSession,
  revokeAuthSession,
  setAuthTokens,
} from '@/shared/auth/session'

afterEach(() => {
  clearAuthSession()
  vi.unstubAllGlobals()
})

describe('authentication session', () => {
  it('revokes the current refresh token when the user signs out', async () => {
    setAuthTokens({
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
    })
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await revokeAuthSession(logout)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/logout',
      expect.objectContaining({
        body: JSON.stringify({ refresh_token: 'refresh-token' }),
        method: 'POST',
      }),
    )
    expect(hasAuthSession()).toBe(false)
  })

  it('clears the browser session when revocation is unavailable', async () => {
    setAuthTokens({
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
    })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network error')))

    await expect(revokeAuthSession(logout)).rejects.toThrow('Network error')
    expect(hasAuthSession()).toBe(false)
  })
})
