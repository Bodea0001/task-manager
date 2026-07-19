export interface User {
  user_id: string
  first_name: string
  last_name: string
  middle_name: string | null
  email: string
  email_verified: boolean
}

export interface AgentRunAllowance {
  used: number
  limit: number
  remaining: number
}
