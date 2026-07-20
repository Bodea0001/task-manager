import type { User } from '@/entities/user/model'
import { apiRequest } from '@/shared/api/http'
import type { AccessToken } from '@/shared/auth/types'

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegistrationData extends LoginCredentials {
  first_name: string
  last_name: string
  middle_name?: string
}

export interface UpdateUserData {
  first_name?: string
  last_name?: string
  middle_name?: string | null
}

export function login(credentials: LoginCredentials): Promise<AccessToken> {
  return apiRequest('/auth/login', {
    auth: 'none',
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}

export function register(data: RegistrationData): Promise<AccessToken> {
  return apiRequest('/auth/register', {
    auth: 'none',
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function logout(): Promise<void> {
  return apiRequest('/auth/logout', {
    auth: 'none',
    method: 'POST',
  })
}

export function getCurrentUser(): Promise<User> {
  return apiRequest('/users/me')
}

export function updateCurrentUser(data: UpdateUserData): Promise<User> {
  return apiRequest('/users/me', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}
