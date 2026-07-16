import type {
  RecurrenceMonthRule,
  RecurrenceFrequency,
  RecurrenceRule,
  RecurrenceOccurrence,
  RecurrenceOccurrenceListResponse,
  RecurrenceTemplate,
  RecurrenceTemplateListResponse,
  UpdateRecurrenceOccurrenceInput,
  Weekday,
} from '@/entities/recurrence/model'
import { apiRequest } from '@/shared/api/http'

export const RECURRENCE_TEMPLATES_QUERY_KEY = ['recurrence-templates'] as const
export const recurrenceTemplateQueryKey = (templateId: string) =>
  [...RECURRENCE_TEMPLATES_QUERY_KEY, templateId] as const
export const recurrenceOccurrencesQueryKey = (
  templateId: string,
  startsAt: string,
  endsAt: string,
) =>
  [
    ...recurrenceTemplateQueryKey(templateId),
    'occurrences',
    startsAt,
    endsAt,
  ] as const

export function listRecurrenceTemplates(): Promise<RecurrenceTemplateListResponse> {
  return apiRequest('/recurrence-templates')
}

export function getRecurrenceTemplate(
  templateId: string,
): Promise<RecurrenceTemplate> {
  return apiRequest(`/recurrence-templates/${templateId}`)
}

export interface CreateRecurrenceTemplateInput {
  title: string
  rules: readonly CreateRecurrenceRuleInput[]
  description?: string
  tag_ids?: readonly string[]
  priority?: RecurrenceTemplate['priority']
}

export function createRecurrenceTemplate(
  data: CreateRecurrenceTemplateInput,
): Promise<RecurrenceTemplate> {
  return apiRequest('/recurrence-templates', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function deleteRecurrenceTemplate(templateId: string): Promise<void> {
  return apiRequest(`/recurrence-templates/${templateId}`, {
    method: 'DELETE',
  })
}

export interface CreateRecurrenceRuleInput {
  frequency: RecurrenceFrequency
  anchor_date: string
  default_time: string
  interval?: number
  default_duration?: string | null
  weekdays?: readonly Weekday[]
  month_rule?: RecurrenceMonthRule | null
  repeat_until?: string
  occurrences_limit?: number
}

export interface UpdateRecurrenceRuleInput {
  anchor_date: string
  default_time: string
  default_duration?: string | null
  repeat_until?: string
  occurrences_limit?: number
}

export function addTagToRecurrenceTemplate(
  templateId: string,
  tagId: string,
): Promise<RecurrenceTemplate> {
  return apiRequest(`/recurrence-templates/${templateId}/tags/${tagId}`, {
    method: 'PUT',
  })
}

export function removeTagFromRecurrenceTemplate(
  templateId: string,
  tagId: string,
): Promise<RecurrenceTemplate> {
  return apiRequest(`/recurrence-templates/${templateId}/tags/${tagId}`, {
    method: 'DELETE',
  })
}

export function createRecurrenceRule(
  templateId: string,
  data: CreateRecurrenceRuleInput,
): Promise<RecurrenceRule> {
  return apiRequest(`/recurrence-templates/${templateId}/rules`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateRecurrenceRule(
  recurrenceId: string,
  data: UpdateRecurrenceRuleInput,
): Promise<RecurrenceRule> {
  return apiRequest(`/recurrence-rules/${recurrenceId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteRecurrenceRule(recurrenceId: string): Promise<void> {
  return apiRequest(`/recurrence-rules/${recurrenceId}`, {
    method: 'DELETE',
  })
}

export function listRecurrenceOccurrences(
  templateId: string,
  startsAt: string,
  endsAt: string,
): Promise<RecurrenceOccurrenceListResponse> {
  const query = new URLSearchParams({ starts_at: startsAt, ends_at: endsAt })
  return apiRequest(
    `/recurrence-templates/${templateId}/occurrences?${query.toString()}`,
  )
}

export function updateRecurrenceOccurrence(
  occurrence: Pick<
    RecurrenceOccurrence,
    'original_starts_at' | 'recurrence_id'
  >,
  data: UpdateRecurrenceOccurrenceInput,
): Promise<RecurrenceOccurrence> {
  return apiRequest(recurrenceOccurrencePath(occurrence), {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function skipRecurrenceOccurrence(
  occurrence: Pick<
    RecurrenceOccurrence,
    'original_starts_at' | 'recurrence_id'
  >,
): Promise<RecurrenceOccurrence> {
  return apiRequest(`${recurrenceOccurrencePath(occurrence)}/skip`, {
    method: 'POST',
  })
}

function recurrenceOccurrencePath(
  occurrence: Pick<
    RecurrenceOccurrence,
    'original_starts_at' | 'recurrence_id'
  >,
): `/${string}` {
  return `/recurrence-rules/${occurrence.recurrence_id}/occurrences/${encodeURIComponent(occurrence.original_starts_at)}`
}
