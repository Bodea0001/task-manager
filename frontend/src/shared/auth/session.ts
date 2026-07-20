import { createApiError } from '@/shared/api/error'
import { environment } from '@/shared/config/environment'
import type { AccessToken, AuthSessionEvent } from '@/shared/auth/types'

const AUTH_SESSION_HINT_KEY = 'task-manager.auth-session-present'
const LEGACY_AUTH_SESSION_STORAGE_KEY = 'task-manager.auth-session'
const AUTH_REFRESH_LOCK_NAME = 'task-manager.auth-refresh'
const ACCESS_TOKEN_LEEWAY_SECONDS = 30

type AuthSessionListener = (event: AuthSessionEvent) => void
type RefreshTokenRevoker = () => Promise<void>

let token: AccessToken | undefined
let refreshInFlight: Promise<AccessToken> | undefined
let sessionRevision = 0
const listeners = new Set<AuthSessionListener>()

removeLegacyStoredTokens()

export function hasAuthSession(): boolean {
  return token !== undefined || readSessionHint()
}

export function setAccessToken(nextToken: AccessToken): void {
  replaceAccessToken(nextToken)
}

export function clearAuthSession(): void {
  const hadSession = token !== undefined || readSessionHint()
  sessionRevision += 1
  token = undefined
  removeSessionHint()

  if (hadSession) notifyListeners('cleared')
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
  const currentToken = token
  if (currentToken === undefined && !readSessionHint()) return undefined
  if (
    currentToken !== undefined &&
    !isAccessTokenExpiring(currentToken.access_token)
  ) {
    return currentToken.access_token
  }

  return (await refreshAuthTokens())?.access_token
}

export async function refreshAuthTokens(
  failedAccessToken?: string,
): Promise<AccessToken | undefined> {
  if (
    failedAccessToken !== undefined &&
    token !== undefined &&
    token.access_token !== failedAccessToken
  ) {
    return token
  }
  if (!hasAuthSession()) return undefined

  refreshInFlight ??= refreshWithCoordination(failedAccessToken).finally(() => {
    refreshInFlight = undefined
  })
  return refreshInFlight
}

async function refreshWithCoordination(
  failedAccessToken?: string,
): Promise<AccessToken> {
  if (navigator.locks === undefined) {
    return requestNewAccessToken()
  }

  return navigator.locks.request(AUTH_REFRESH_LOCK_NAME, () => {
    if (
      failedAccessToken !== undefined &&
      token !== undefined &&
      token.access_token !== failedAccessToken
    ) {
      return token
    }
    return requestNewAccessToken()
  })
}

async function requestNewAccessToken(): Promise<AccessToken> {
  const expectedRevision = sessionRevision
  const response = await fetch(`${environment.apiBaseUrl}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    const error = await createApiError(response)
    if (response.status === 401 && expectedRevision === sessionRevision) {
      clearAuthSession()
    }
    throw error
  }

  const nextToken = (await response.json()) as unknown
  if (!isAccessToken(nextToken)) {
    throw new Error('The authentication response is invalid')
  }
  if (expectedRevision !== sessionRevision) {
    throw new Error('The authentication session changed during token refresh')
  }

  replaceAccessToken(nextToken)
  return nextToken
}

async function revokeCurrentSession(
  revokeRefreshToken: RefreshTokenRevoker,
): Promise<void> {
  clearAuthSession()
  await revokeRefreshToken()
}

function replaceAccessToken(nextToken: AccessToken): void {
  sessionRevision += 1
  token = nextToken
  persistSessionHint()
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
  if (payload === undefined) return undefined

  try {
    const normalized = payload.replaceAll('-', '+').replaceAll('_', '/')
    const padding = '='.repeat((4 - (normalized.length % 4)) % 4)
    const parsed = JSON.parse(atob(normalized + padding)) as { exp?: unknown }
    return typeof parsed.exp === 'number' ? parsed.exp : undefined
  } catch {
    return undefined
  }
}

function isAccessToken(value: unknown): value is AccessToken {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Partial<AccessToken>
  return (
    typeof candidate.access_token === 'string' &&
    candidate.access_token.length > 0 &&
    typeof candidate.token_type === 'string' &&
    candidate.token_type.toLowerCase() === 'bearer'
  )
}

function readSessionHint(): boolean {
  try {
    return localStorage.getItem(AUTH_SESSION_HINT_KEY) === '1'
  } catch {
    return false
  }
}

function persistSessionHint(): void {
  try {
    localStorage.setItem(AUTH_SESSION_HINT_KEY, '1')
  } catch {
    // The access token remains available in memory for this page.
  }
}

function removeSessionHint(): void {
  try {
    localStorage.removeItem(AUTH_SESSION_HINT_KEY)
  } catch {
    // In-memory authentication can still be cleared.
  }
}

function removeLegacyStoredTokens(): void {
  try {
    localStorage.removeItem(LEGACY_AUTH_SESSION_STORAGE_KEY)
  } catch {
    // Legacy browser storage is best-effort cleanup only.
  }
}

function notifyListeners(event: AuthSessionEvent): void {
  for (const listener of listeners) listener(event)
}

window.addEventListener('storage', (event) => {
  if (event.key !== AUTH_SESSION_HINT_KEY) return

  if (event.newValue === '1') {
    notifyListeners('changed')
    return
  }

  sessionRevision += 1
  token = undefined
  notifyListeners('cleared')
})
