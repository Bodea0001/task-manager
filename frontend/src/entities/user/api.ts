import type { AgentRunAllowance } from '@/entities/user/model'
import { apiRequest } from '@/shared/api/http'

export const AGENT_RUN_ALLOWANCE_QUERY_KEY = [
  'users',
  'me',
  'agent',
  'usage',
] as const

export function getAgentRunAllowance(): Promise<AgentRunAllowance> {
  return apiRequest('/users/me/agent/usage')
}
