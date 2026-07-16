import { ApiError } from '@/shared/api/http'

export interface FormApiError {
  code: string
  fallbackMessage: string
  fieldErrors: Readonly<Record<string, string>>
  generalErrors: readonly string[]
  requestId?: string
}

export interface FormApiErrorOptions {
  aliases?: Readonly<Record<string, string>>
  fields: readonly string[]
}

export function toFormApiError(
  error: unknown,
  options: FormApiErrorOptions,
): FormApiError | undefined {
  if (!(error instanceof ApiError)) return undefined

  const fields = new Set(options.fields)
  const fieldErrors: Record<string, string> = {}
  const generalErrors: string[] = []

  for (const detail of error.details || []) {
    const message = detail.message?.trim()
    if (message === undefined || message.length === 0) continue
    const field = resolveField(detail.location, fields, options.aliases)
    if (field === undefined) {
      generalErrors.push(message)
    } else {
      fieldErrors[field] ??= message
    }
  }

  return {
    code: error.code,
    fallbackMessage: error.message,
    fieldErrors,
    generalErrors,
    requestId: error.requestId,
  }
}

export function clearFormApiField(
  error: FormApiError | undefined,
  field: string,
): FormApiError | undefined {
  if (error === undefined || error.fieldErrors[field] === undefined) return error
  const fieldErrors = { ...error.fieldErrors }
  delete fieldErrors[field]
  return Object.keys(fieldErrors).length === 0 && error.generalErrors.length === 0
    ? undefined
    : { ...error, fieldErrors }
}

function resolveField(
  location: readonly (number | string)[] | undefined,
  fields: ReadonlySet<string>,
  aliases: Readonly<Record<string, string>> | undefined,
): string | undefined {
  const segments = (location || [])
    .filter((part): part is string => typeof part === 'string')
    .filter((part) => part !== 'body' && part !== 'query' && part !== 'path')
  const candidates = segments.flatMap((_, index) => [
    segments.slice(index).join('.'),
  ])

  for (const candidate of candidates) {
    const field = aliases?.[candidate] || candidate
    if (fields.has(field)) return field
  }
  return undefined
}
