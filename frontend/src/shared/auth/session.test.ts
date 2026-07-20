import { afterEach, describe, expect, it, vi } from 'vitest'

import { logout } from '@/features/auth/api'
import {
  clearAuthSession,
  hasAuthSession,
  revokeAuthSession,
  setAccessToken,
} from '@/shared/auth/session'

afterEach(() => {
  clearAuthSession()
  vi.unstubAllGlobals()
})

describe('authentication session', () => {
  it('revokes the cookie-managed session when the user signs out', async () => {
    setAccessToken({
      access_token: 'access-token',
      token_type: 'bearer',
    })
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await revokeAuthSession(logout)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/logout',
      expect.objectContaining({
        credentials: 'include',
        method: 'POST',
      }),
    )
    expect(hasAuthSession()).toBe(false)
  })

  it('clears the browser session when revocation is unavailable', async () => {
    setAccessToken({
      access_token: 'access-token',
      token_type: 'bearer',
    })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network error')))

    await expect(revokeAuthSession(logout)).rejects.toThrow('Network error')
    expect(hasAuthSession()).toBe(false)
  })

  it('never persists an access or refresh token in browser storage', () => {
    setAccessToken({
      access_token: 'sensitive-access-token',
      token_type: 'bearer',
    })

    const storedValues = Array.from(
      { length: localStorage.length },
      (_, index) => localStorage.getItem(localStorage.key(index) ?? ''),
    )
    expect(storedValues).not.toContain('sensitive-access-token')
    expect(localStorage.getItem('task-manager.auth-session')).toBeNull()
    expect(localStorage.getItem('task-manager.auth-session-present')).toBe('1')
  })
})
