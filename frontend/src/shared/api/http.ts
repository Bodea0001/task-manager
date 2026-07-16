import { createApiError } from '@/shared/api/error'
import { getAccessToken, refreshAuthTokens } from '@/shared/auth/session'
import { environment } from '@/shared/config/environment'

export { ApiError } from '@/shared/api/error'

export interface ApiRequestInit extends RequestInit {
  auth?: 'none' | 'required'
}

export async function apiRequest<T>(
  path: `/${string}`,
  init: ApiRequestInit = {},
): Promise<T> {
  const { auth = 'required', ...requestInit } = init
  const accessToken = auth === 'required' ? await getAccessToken() : undefined
  let response = await sendRequest(path, requestInit, accessToken)

  if (auth === 'required' && response.status === 401) {
    const nextTokens = await refreshAuthTokens(accessToken)
    if (nextTokens !== undefined) {
      response = await sendRequest(path, requestInit, nextTokens.access_token)
    }
  }

  return readResponse<T>(response)
}

export async function apiStreamRequest(
  path: `/${string}`,
  init: ApiRequestInit = {},
): Promise<Response> {
  const { auth = 'required', ...requestInit } = init
  const headers = new Headers(requestInit.headers)
  headers.set('Accept', 'text/event-stream')
  const streamInit = { ...requestInit, headers }
  const accessToken = auth === 'required' ? await getAccessToken() : undefined
  let response = await sendRequest(path, streamInit, accessToken)

  if (auth === 'required' && response.status === 401) {
    const nextTokens = await refreshAuthTokens(accessToken)
    if (nextTokens !== undefined) {
      response = await sendRequest(path, streamInit, nextTokens.access_token)
    }
  }

  if (!response.ok) throw await createApiError(response)
  return response
}

async function sendRequest(
  path: `/${string}`,
  init: RequestInit,
  accessToken?: string,
): Promise<Response> {
  const headers = new Headers(init.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')

  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (accessToken !== undefined) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  return fetch(`${environment.apiBaseUrl}${path}`, {
    ...init,
    headers,
  })
}

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw await createApiError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}
