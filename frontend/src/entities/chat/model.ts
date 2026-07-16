export type ChatMessageRole = 'assistant' | 'user'

export interface Chat {
  chat_id: string
  title: string
  is_active: boolean
  created_at: string
}

export interface ChatListResponse {
  chats: readonly Chat[]
  next_offset: number | null
}

export interface ChatMessage {
  message_id: string
  chat_id: string
  role: ChatMessageRole
  content: string
  created_at: string
}

export interface ChatMessageListResponse {
  messages: readonly ChatMessage[]
  next_offset: number | null
}

export type PlanStatus = 'executable' | 'needs_clarification'
export type PlanStepStatus = 'completed' | 'failed' | 'in_progress' | 'pending'
export type AgentResultStatus = 'completed' | 'needs_clarification' | 'rejected'

export interface AgentPlanStep {
  step_id: string
  title: string
  status: PlanStepStatus
}

export interface AgentPlan {
  objective: string
  status: PlanStatus
  steps: readonly AgentPlanStep[]
}

export interface AgentResult {
  status: AgentResultStatus
  message: string
  data: Record<string, unknown>
}

export interface AgentStreamError {
  code: string
  message: string
  request_id: string
}
