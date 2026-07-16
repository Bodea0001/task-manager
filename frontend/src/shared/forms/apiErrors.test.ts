import { describe, expect, it } from 'vitest'

import { ApiError } from '@/shared/api/http'
import {
  clearFormApiField,
  toFormApiError,
} from '@/shared/forms/apiErrors'

describe('form API errors', () => {
  it('maps nested server locations to form fields and preserves support context', () => {
    const error = new ApiError(422, {
      code: 'request_validation_error',
      message: 'Request validation failed',
      request_id: 'request-id',
      details: [
        {
          location: ['body', 'schedule', 'starts_at'],
          message: 'Start time is invalid',
          type: 'value_error',
        },
        {
          location: ['body', 'unknown'],
          message: 'Another constraint failed',
        },
      ],
    })

    const result = toFormApiError(error, {
      fields: ['starts_at'],
      aliases: { 'schedule.starts_at': 'starts_at' },
    })

    expect(result).toMatchObject({
      code: 'request_validation_error',
      fieldErrors: { starts_at: 'Start time is invalid' },
      generalErrors: ['Another constraint failed'],
      requestId: 'request-id',
    })
    expect(clearFormApiField(result, 'starts_at')?.fieldErrors).toEqual({})
  })
})
