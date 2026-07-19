export interface User {
  user_id: string
  first_name: string
  last_name: string
  middle_name: string | null
  email: string
  email_verified: boolean
}

export type AgentAccessLevel = 'limited' | 'unmetered'

interface AgentRunAllowanceBase {
  used: number
}

export type AgentRunAllowance =
  | (AgentRunAllowanceBase & {
      access_level: 'limited'
      limit: number
      remaining: number
    })
  | (AgentRunAllowanceBase & {
      access_level: 'unmetered'
      limit: null
      remaining: null
    })
