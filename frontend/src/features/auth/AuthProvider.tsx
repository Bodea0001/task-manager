import {
  createContext,
  createSignal,
  onCleanup,
  onMount,
  type Accessor,
  type ParentProps,
  useContext,
} from 'solid-js'
import { useQueryClient } from '@tanstack/solid-query'

import type { User } from '@/entities/user/model'
import {
  getCurrentUser,
  login as requestLogin,
  logout as requestLogout,
  register as requestRegistration,
  updateCurrentUser,
  type LoginCredentials,
  type RegistrationData,
  type UpdateUserData,
} from '@/features/auth/api'
import { ApiError } from '@/shared/api/http'
import {
  clearAuthSession,
  getAccessToken,
  hasAuthSession,
  revokeAuthSession,
  setAccessToken,
  subscribeToAuthSession,
} from '@/shared/auth/session'
import type { AccessToken } from '@/shared/auth/types'

export type AuthStatus =
  | 'anonymous'
  | 'authenticated'
  | 'initializing'
  | 'unavailable'

interface AuthContextValue {
  status: Accessor<AuthStatus>
  user: Accessor<User | undefined>
  login: (credentials: LoginCredentials) => Promise<void>
  register: (data: RegistrationData) => Promise<void>
  updateUser: (data: UpdateUserData) => Promise<User>
  logout: () => Promise<void>
  retryInitialization: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>()

export function AuthProvider(props: ParentProps) {
  const queryClient = useQueryClient()
  const [status, setStatus] = createSignal<AuthStatus>('initializing')
  const [user, setUser] = createSignal<User>()

  const initialize = async () => {
    if (!hasAuthSession()) {
      setUser()
      setStatus('anonymous')
      return
    }

    setStatus('initializing')
    try {
      await getAccessToken()
      setUser(await getCurrentUser())
      setStatus('authenticated')
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearAuthSession()
        setUser()
        setStatus('anonymous')
        return
      }
      setStatus('unavailable')
    }
  }

  const authenticate = async (
    requestToken: () => Promise<AccessToken>,
  ): Promise<void> => {
    const nextToken = await requestToken()
    queryClient.clear()
    setAccessToken(nextToken)
    try {
      setUser(await getCurrentUser())
      setStatus('authenticated')
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearAuthSession()
      }
      throw error
    }
  }

  const login = (credentials: LoginCredentials) =>
    authenticate(() => requestLogin(credentials))

  const register = (data: RegistrationData) =>
    authenticate(() => requestRegistration(data))

  const updateUser = async (data: UpdateUserData): Promise<User> => {
    const updatedUser = await updateCurrentUser(data)
    setUser(updatedUser)
    return updatedUser
  }

  const logout = async (): Promise<void> => {
    queryClient.clear()
    try {
      await revokeAuthSession(requestLogout)
    } catch {
      // Local logout must still succeed when the endpoint is unavailable.
    } finally {
      clearAuthSession()
      setUser()
      setStatus('anonymous')
    }
  }

  const unsubscribe = subscribeToAuthSession((event) => {
    if (event === 'cleared') {
      queryClient.clear()
      setUser()
      setStatus('anonymous')
      return
    }
    void initialize()
  })

  onMount(() => void initialize())
  onCleanup(unsubscribe)

  return (
    <AuthContext.Provider
      value={{
        status,
        user,
        login,
        register,
        updateUser,
        logout,
        retryInitialization: initialize,
      }}
    >
      {props.children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
