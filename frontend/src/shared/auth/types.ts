export interface AccessToken {
  access_token: string
  token_type: string
}

export type AuthSessionEvent = 'changed' | 'cleared'
