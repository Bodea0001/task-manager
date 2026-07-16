import { createApiError } from '@/shared/api/error'
import { environment } from '@/shared/config/environment'
import type { AuthSessionEvent, AuthTokens } from '@/shared/auth/types'

const AUTH_SESSION_STORAGE_KEY = 'task-manager.auth-session'
const AUTH_REFRESH_LOCK_NAME = 'task-manager.auth-refresh'
const ACCESS_TOKEN_LEEWAY_SECONDS = 30

type AuthSessionListener = (event: AuthSessionEvent) => void
type RefreshTokenRevoker = (refreshToken: string) => Promise<void>

let tokens = readStoredTokens()
let refreshInFlight: Promise<AuthTokens> | undefined
const listeners = new Set<AuthSessionListener>()

export function hasAuthSession(): boolean {
  return tokens !== undefined
}

export function setAuthTokens(nextTokens: AuthTokens): void {
  tokens = nextTokens
  persistTokens(nextTokens)
  notifyListeners('changed')
}

export function clearAuthSession(): void {
  const hadSession = tokens !== undefined
  tokens = undefined
  removeStoredTokens()

  if (hadSession) {
    notifyListeners('cleared')
  }
}

export function subscribeToAuthSession(listener: AuthSessionListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export async function revokeAuthSession(
  revokeRefreshToken: RefreshTokenRevoker,
): Promise<void> {
  await refreshInFlight?.catch(() => undefined)

  if (navigator.locks === undefined) {
    return revokeCurrentSession(revokeRefreshToken)
  }

  return navigator.locks.request(AUTH_REFRESH_LOCK_NAME, () =>
    revokeCurrentSession(revokeRefreshToken),
  )
}

export async function getAccessToken(): Promise<string | undefined> {
  const currentTokens = tokens
  if (currentTokens === undefined) {
    return undefined
  }

  if (!isAccessTokenExpiring(currentTokens.access_token)) {
    return currentTokens.access_token
  }

  return (await refreshAuthTokens())?.access_token
}

export async function refreshAuthTokens(
  failedAccessToken?: string,
): Promise<AuthTokens | undefined> {
  if (
    failedAccessToken !== undefined &&
    tokens !== undefined &&
    tokens.access_token !== failedAccessToken
  ) {
    return tokens
  }

  if (tokens === undefined) {
    return undefined
  }

  refreshInFlight ??= refreshWithCoordination(tokens.refresh_token).finally(() => {
    refreshInFlight = undefined
  })
  return refreshInFlight
}

async function refreshWithCoordination(refreshToken: string): Promise<AuthTokens> {
  if (navigator.locks === undefined) {
    return requestNewTokens(refreshToken)
  }

  return navigator.locks.request(AUTH_REFRESH_LOCK_NAME, async () => {
    const storedTokens = readStoredTokens()
    if (
      storedTokens !== undefined &&
      storedTokens.refresh_token !== refreshToken
    ) {
      tokens = storedTokens
      notifyListeners('changed')
      return storedTokens
    }
    return requestNewTokens(refreshToken)
  })
}

async function requestNewTokens(refreshToken: string): Promise<AuthTokens> {
  const wasPersisted =
    readStoredTokens()?.refresh_token === refreshToken
  const response = await fetch(`${environment.apiBaseUrl}/auth/refresh`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })

  if (!response.ok) {
    const storedTokens = readStoredTokens()
    if (
      response.status === 401 &&
      storedTokens !== undefined &&
      storedTokens.refresh_token !== refreshToken
    ) {
      tokens = storedTokens
      notifyListeners('changed')
      return storedTokens
    }

    const error = await createApiError(response)
    if (response.status === 401 && tokens?.refresh_token === refreshToken) {
      clearAuthSession()
    }
    throw error
  }

  const nextTokens = (await response.json()) as unknown
  if (!isAuthTokens(nextTokens)) {
    throw new Error('The authentication response is invalid')
  }

  const storedTokens = readStoredTokens()
  if (wasPersisted && storedTokens === undefined) {
    tokens = undefined
    notifyListeners('cleared')
    throw new Error('The authentication session changed during token refresh')
  }
  if (
    storedTokens !== undefined &&
    storedTokens.refresh_token !== refreshToken
  ) {
    tokens = storedTokens
    notifyListeners('changed')
    return storedTokens
  }
  if (tokens?.refresh_token !== refreshToken) {
    if (tokens !== undefined) {
      return tokens
    }
    throw new Error('The authentication session changed during token refresh')
  }

  setAuthTokens(nextTokens)
  return nextTokens
}

async function revokeCurrentSession(
  revokeRefreshToken: RefreshTokenRevoker,
): Promise<void> {
  const currentTokens = readStoredTokens() ?? tokens
  clearAuthSession()

  if (currentTokens !== undefined) {
    await revokeRefreshToken(currentTokens.refresh_token)
  }
}

function isAccessTokenExpiring(accessToken: string): boolean {
  const expiresAt = readJwtExpiration(accessToken)
  return (
    expiresAt !== undefined &&
    expiresAt <= Math.floor(Date.now() / 1000) + ACCESS_TOKEN_LEEWAY_SECONDS
  )
}

function readJwtExpiration(accessToken: string): number | undefined {
  const payload = accessToken.split('.')[1]
  if (payload === undefined) {
    return undefined
  }

  try {
    const normalized = payload.replaceAll('-', '+').replaceAll('_', '/')
    const padding = '='.repeat((4 - (normalized.length % 4)) % 4)
    const parsed = JSON.parse(atob(normalized + padding)) as { exp?: unknown }
    return typeof parsed.exp === 'number' ? parsed.exp : undefined
  } catch {
    return undefined
  }
}

function readStoredTokens(): AuthTokens | undefined {
  try {
    const value = localStorage.getItem(AUTH_SESSION_STORAGE_KEY)
    if (value === null) {
      return undefined
    }
    const parsed = JSON.parse(value) as unknown
    return isAuthTokens(parsed) ? parsed : undefined
  } catch {
    return undefined
  }
}

function persistTokens(nextTokens: AuthTokens): void {
  try {
    localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(nextTokens))
  } catch {
    // The session remains available until this page is closed.
  }
}

function removeStoredTokens(): void {
  try {
    localStorage.removeItem(AUTH_SESSION_STORAGE_KEY)
  } catch {
    // An in-memory session can still be cleared without storage access.
  }
}

function isAuthTokens(value: unknown): value is AuthTokens {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const candidate = value as Partial<AuthTokens>
  return (
    typeof candidate.access_token === 'string' &&
    candidate.access_token.length > 0 &&
    typeof candidate.refresh_token === 'string' &&
    candidate.refresh_token.length > 0 &&
    typeof candidate.token_type === 'string' &&
    candidate.token_type.toLowerCase() === 'bearer'
  )
}

function notifyListeners(event: AuthSessionEvent): void {
  for (const listener of listeners) {
    listener(event)
  }
}

window.addEventListener('storage', (event) => {
  if (event.key !== AUTH_SESSION_STORAGE_KEY) {
    return
  }

  const nextTokens = readStoredTokens()
  const eventType: AuthSessionEvent =
    nextTokens === undefined ? 'cleared' : 'changed'
  tokens = nextTokens
  notifyListeners(eventType)
})
