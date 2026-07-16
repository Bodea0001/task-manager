export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

export type AuthSessionEvent = 'changed' | 'cleared'
