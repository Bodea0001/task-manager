import type { QueryClient } from '@tanstack/solid-query'

import {
  RECURRENCE_TEMPLATES_QUERY_KEY,
  recurrenceTemplateQueryKey,
} from '@/entities/recurrence/api'
import type {
  RecurrenceRule,
  RecurrenceTemplate,
  RecurrenceTemplateListResponse,
} from '@/entities/recurrence/model'

export function storeRecurrenceTemplate(
  queryClient: QueryClient,
  template: RecurrenceTemplate,
): void {
  queryClient.setQueryData<RecurrenceTemplateListResponse>(
    RECURRENCE_TEMPLATES_QUERY_KEY,
    (current) =>
      current === undefined
        ? current
        : {
            templates: current.templates.map((item) =>
              item.template_id === template.template_id ? template : item,
            ),
          },
  )
  queryClient.setQueryData(
    recurrenceTemplateQueryKey(template.template_id),
    template,
  )
}

export function addRecurrenceTemplateToCache(
  queryClient: QueryClient,
  template: RecurrenceTemplate,
): void {
  queryClient.setQueryData<RecurrenceTemplateListResponse>(
    RECURRENCE_TEMPLATES_QUERY_KEY,
    (current) =>
      current === undefined
        ? current
        : { templates: [template, ...current.templates] },
  )
  queryClient.setQueryData(
    recurrenceTemplateQueryKey(template.template_id),
    template,
  )
}

export function removeRecurrenceTemplateFromCache(
  queryClient: QueryClient,
  templateId: string,
): void {
  queryClient.setQueryData<RecurrenceTemplateListResponse>(
    RECURRENCE_TEMPLATES_QUERY_KEY,
    (current) =>
      current === undefined
        ? current
        : {
            templates: current.templates.filter(
              (template) => template.template_id !== templateId,
            ),
          },
  )
  queryClient.removeQueries({ queryKey: recurrenceTemplateQueryKey(templateId) })
}

export function storeRecurrenceRule(
  queryClient: QueryClient,
  rule: RecurrenceRule,
): void {
  updateTemplates(queryClient, (template) =>
    template.template_id === rule.template_id
      ? { ...template, rules: upsertRule(template.rules, rule) }
      : template,
  )
  queryClient.setQueryData<RecurrenceTemplate>(
    recurrenceTemplateQueryKey(rule.template_id),
    (template) =>
      template === undefined
        ? template
        : { ...template, rules: upsertRule(template.rules, rule) },
  )
}

export function removeRecurrenceRuleFromCache(
  queryClient: QueryClient,
  templateId: string,
  recurrenceId: string,
): void {
  const removeRule = (template: RecurrenceTemplate) => ({
    ...template,
    rules: template.rules.filter(
      (rule) => rule.recurrence_id !== recurrenceId,
    ),
  })
  updateTemplates(queryClient, (template) =>
    template.template_id === templateId ? removeRule(template) : template,
  )
  queryClient.setQueryData<RecurrenceTemplate>(
    recurrenceTemplateQueryKey(templateId),
    (template) => (template === undefined ? template : removeRule(template)),
  )
}

function updateTemplates(
  queryClient: QueryClient,
  update: (template: RecurrenceTemplate) => RecurrenceTemplate,
): void {
  queryClient.setQueryData<RecurrenceTemplateListResponse>(
    RECURRENCE_TEMPLATES_QUERY_KEY,
    (current) =>
      current === undefined
        ? current
        : { templates: current.templates.map(update) },
  )
}

function upsertRule(
  rules: readonly RecurrenceRule[],
  updatedRule: RecurrenceRule,
): readonly RecurrenceRule[] {
  const index = rules.findIndex(
    (rule) => rule.recurrence_id === updatedRule.recurrence_id,
  )
  if (index === -1) {
    return [...rules, updatedRule]
  }
  return rules.map((rule) =>
    rule.recurrence_id === updatedRule.recurrence_id ? updatedRule : rule,
  )
}
