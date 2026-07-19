import type { ApiErrorResponse } from '@/shared/api/types'

export class ApiError extends Error {
  readonly code: string
  readonly context: ApiErrorResponse['context']
  readonly details: ApiErrorResponse['details']
  readonly requestId: string | undefined
  readonly status: number

  constructor(status: number, response: ApiErrorResponse) {
    super(response.message)
    this.name = 'ApiError'
    this.status = status
    this.code = response.code
    this.context = response.context
    this.details = response.details
    this.requestId = response.request_id
  }
}

export async function createApiError(response: Response): Promise<ApiError> {
  const fallback: ApiErrorResponse = {
    code: 'unexpected_response',
    message: 'The server could not complete the request',
  }

  try {
    const body = (await response.json()) as Partial<ApiErrorResponse>
    return new ApiError(response.status, {
      code: body.code || fallback.code,
      context: body.context,
      details: body.details,
      message: body.message || fallback.message,
      request_id: body.request_id,
    })
  } catch {
    return new ApiError(response.status, fallback)
  }
}
