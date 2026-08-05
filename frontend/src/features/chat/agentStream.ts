import type {
  AgentPlan,
  AgentResult,
  AgentStreamError,
} from '@/entities/chat/model'
import { apiStreamRequest } from '@/shared/api/http'

export type AgentStreamHandlers = {
  onError: (error: AgentStreamError) => void
  onPlan: (plan: AgentPlan) => void
  onResult: (result: AgentResult) => void
}

export async function runAgentStream(
  chatId: string,
  message: string,
  handlers: AgentStreamHandlers,
): Promise<void> {
  await streamAgentResponse(
    `/chats/${chatId}/agent`,
    {
      method: 'POST',
      body: JSON.stringify({ message }),
    },
    handlers,
  )
}

export async function retryAgentStream(
  chatId: string,
  handlers: AgentStreamHandlers,
): Promise<void> {
  await streamAgentResponse(
    `/chats/${chatId}/agent/retry`,
    { method: 'POST' },
    handlers,
  )
}

async function streamAgentResponse(
  path: `/${string}`,
  init: RequestInit,
  handlers: AgentStreamHandlers,
): Promise<void> {
  const response = await apiStreamRequest(path, init)
  if (response.body === null) {
    throw new Error('The agent response stream is unavailable')
  }

  let terminalEventReceived = false
  await readEventStream(response.body, (event, data) => {
    if (event === 'plan') handlers.onPlan(JSON.parse(data) as AgentPlan)
    if (event === 'result') {
      terminalEventReceived = true
      handlers.onResult(JSON.parse(data) as AgentResult)
    }
    if (event === 'error') {
      terminalEventReceived = true
      handlers.onError(JSON.parse(data) as AgentStreamError)
    }
  })
  if (!terminalEventReceived) throw new Error('The agent response stream ended early')
}

async function readEventStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: string, data: string) => void,
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const chunk = await reader.read()
    buffer += decoder.decode(chunk.value, { stream: !chunk.done })
    const records = buffer.split(/\r?\n\r?\n/)
    buffer = records.pop() || ''
    for (const record of records) parseEvent(record, onEvent)
    if (chunk.done) break
  }

  if (buffer.trim().length > 0) parseEvent(buffer, onEvent)
}

function parseEvent(
  record: string,
  onEvent: (event: string, data: string) => void,
): void {
  let event = 'message'
  const data: string[] = []

  for (const line of record.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }

  if (data.length > 0 && event !== 'heartbeat') {
    onEvent(event, data.join('\n'))
  }
}
