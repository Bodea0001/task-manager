import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiRequest } from '@/shared/api/http'
import {
  clearAuthSession,
  hasAuthSession,
  setAccessToken,
} from '@/shared/auth/session'

afterEach(() => {
  clearAuthSession()
  vi.unstubAllGlobals()
})

describe('API requests', () => {
  it('returns the response body for a successful request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: 'ok' }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        }),
      ),
    )

    await expect(apiRequest<{ status: string }>('/status')).resolves.toEqual({
      status: 'ok',
    })
  })

  it('preserves the public error contract for presentation logic', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: 'request_validation_error',
            message: 'Request validation failed',
            request_id: 'request-id',
            details: [{ location: ['body', 'title'], type: 'value_error' }],
          }),
          { status: 422 },
        ),
      ),
    )

    const error = await apiRequest('/tasks').catch(
      (reason: unknown) => reason,
    )

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      code: 'request_validation_error',
      requestId: 'request-id',
      status: 422,
    })
  })

  it('refreshes an expired session before sending a protected request', async () => {
    setAccessToken({
      access_token: createAccessToken(-60),
      token_type: 'bearer',
    })
    const nextAccessToken = createAccessToken(3_600)
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input] = args
      const url = String(input)
      if (url.endsWith('/auth/refresh')) {
        return Promise.resolve(jsonResponse({
          access_token: nextAccessToken,
          token_type: 'bearer',
        }))
      }

      return Promise.resolve(jsonResponse({ status: 'ok' }))
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiRequest('/tasks')).resolves.toEqual({ status: 'ok' })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/auth/refresh')
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBeUndefined()
    expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe('include')
    expect(
      new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get('Authorization'),
    ).toBe(`Bearer ${nextAccessToken}`)
  })

  it('shares one token refresh between concurrent protected requests', async () => {
    setAccessToken({
      access_token: createAccessToken(-60),
      token_type: 'bearer',
    })
    let refreshRequests = 0
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input] = args
      if (String(input).endsWith('/auth/refresh')) {
        refreshRequests += 1
        return Promise.resolve(jsonResponse({
          access_token: createAccessToken(3_600),
          token_type: 'bearer',
        }))
      }
      return Promise.resolve(jsonResponse({ status: 'ok' }))
    })
    vi.stubGlobal('fetch', fetchMock)

    await Promise.all([apiRequest('/tasks'), apiRequest('/tags')])

    expect(refreshRequests).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('refreshes and retries once after an unexpected unauthorized response', async () => {
    const oldAccessToken = createAccessToken(3_600)
    const nextAccessToken = createAccessToken(7_200)
    setAccessToken({
      access_token: oldAccessToken,
      token_type: 'bearer',
    })
    let taskRequests = 0
    const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
      const [input] = args
      if (String(input).endsWith('/auth/refresh')) {
        return Promise.resolve(jsonResponse({
          access_token: nextAccessToken,
          token_type: 'bearer',
        }))
      }

      taskRequests += 1
      return Promise.resolve(
        taskRequests === 1
          ? jsonResponse({ code: 'invalid_token', message: 'Invalid token' }, 401)
          : jsonResponse({ status: 'ok' }),
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiRequest('/tasks')).resolves.toEqual({ status: 'ok' })

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(
      new Headers(fetchMock.mock.calls[2]?.[1]?.headers).get('Authorization'),
    ).toBe(`Bearer ${nextAccessToken}`)
  })

  it('clears a session when its refresh token is rejected', async () => {
    setAccessToken({
      access_token: createAccessToken(-60),
      token_type: 'bearer',
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          { code: 'invalid_token', message: 'Invalid token' },
          401,
        ),
      ),
    )

    await expect(apiRequest('/tasks')).rejects.toMatchObject({
      code: 'invalid_token',
      status: 401,
    })
    expect(hasAuthSession()).toBe(false)
  })

  it('does not restore a session when logout happens during refresh', async () => {
    setAccessToken({
      access_token: createAccessToken(-60),
      token_type: 'bearer',
    })
    let resolveRefresh: (response: Response) => void = () => undefined
    const refreshResponse = new Promise<Response>((resolve) => {
      resolveRefresh = resolve
    })
    const fetchMock = vi.fn(() => refreshResponse)
    vi.stubGlobal('fetch', fetchMock)

    const request = apiRequest('/tasks')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    clearAuthSession()
    resolveRefresh(jsonResponse({
      access_token: createAccessToken(3_600),
      token_type: 'bearer',
    }))

    await expect(request).rejects.toThrow()
    expect(hasAuthSession()).toBe(false)
  })
})

function createAccessToken(expiresInSeconds: number): string {
  const payload = btoa(
    JSON.stringify({ exp: Math.floor(Date.now() / 1000) + expiresInSeconds }),
  )
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replaceAll('=', '')
  return `header.${payload}.signature`
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })
}
