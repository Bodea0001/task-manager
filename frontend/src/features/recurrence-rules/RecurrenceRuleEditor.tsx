import { createMutation, useQueryClient } from '@tanstack/solid-query'
import AlertTriangle from 'lucide-solid/icons/triangle-alert'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import { createSignal, Show, untrack } from 'solid-js'

import './recurrence-rule-editor.css'
import '@/features/recurrence-mutations/recurrence-mutations.css'

import {
  createRecurrenceRule,
  updateRecurrenceRule,
} from '@/entities/recurrence/api'
import { storeRecurrenceRule } from '@/entities/recurrence/cache'
import type { RecurrenceRule } from '@/entities/recurrence/model'
import { invalidateTaskLists } from '@/entities/task/cache'
import {
  recurrenceFieldLabels,
  RecurrenceRuleFields,
} from '@/features/recurrence-rules/RecurrenceRuleFields'
import { createRecurrenceRuleForm } from '@/features/recurrence-rules/recurrenceRuleForm'
import { ApiError } from '@/shared/api/http'
import { type FormApiError, toFormApiError } from '@/shared/forms/apiErrors'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import {
  createUnsavedChangesGuard,
  UnsavedChangesDialog,
} from '@/shared/navigation/UnsavedChangesGuard'
import { FormErrorSummary } from '@/shared/ui/FormErrorSummary'

export function RecurrenceRuleEditor(props: {
  onClose: () => void
  rule?: RecurrenceRule
  templateId: string
}) {
  const queryClient = useQueryClient()
  const { t } = useI18n()
  const initialRule = untrack(() => props.rule)
  const form = createRecurrenceRuleForm(initialRule)
  const [isConfirmationOpen, setConfirmationOpen] = createSignal(false)
  const [errorKey, setErrorKey] = createSignal<TranslationKey>()
  const [apiError, setApiError] = createSignal<FormApiError>()
  const navigationGuard = createUnsavedChangesGuard(form.isDirty)
  const isEditing = () => initialRule !== undefined
  const mutation = createMutation(() => ({
    mutationFn: () => {
      return initialRule === undefined
        ? createRecurrenceRule(props.templateId, form.buildCreateInput())
        : updateRecurrenceRule(
            initialRule.recurrence_id,
            form.buildUpdateInput(),
          )
    },
    onSuccess: (rule) => {
      storeRecurrenceRule(queryClient, rule)
      void invalidateTaskLists(queryClient)
      props.onClose()
    },
  }))

  const closeConfirmation = () => {
    setConfirmationOpen(false)
    setErrorKey()
    setApiError()
  }

  const requestConfirmation = () => {
    setErrorKey()
    setApiError()
    if (!form.isValid()) {
      setErrorKey('recurring.rules.editor.validation')
      return
    }
    setConfirmationOpen(true)
  }

  const save = async () => {
    setErrorKey()
    setApiError()
    try {
      await mutation.mutateAsync()
    } catch (error) {
      setApiError(
        toFormApiError(error, {
          fields: [
            'frequency',
            'interval',
            'weekdays',
            'month_rule_mode',
            'month_day',
            'ordinal_week',
            'ordinal_weekday',
            'business_day_policy',
            'anchor_date',
            'default_time',
            'duration_hours',
            'duration_minutes',
            'end_mode',
            'repeat_until',
            'occurrences_limit',
          ],
          aliases: {
            default_duration: 'duration_hours',
            month_rule: 'month_rule_mode',
          },
        }),
      )
      setConfirmationOpen(false)
      setErrorKey(
        error instanceof ApiError && error.code === 'task_schedule_overlap'
          ? 'recurring.rules.editor.overlap'
          : 'recurring.rules.editor.mutationError',
      )
    }
  }

  return (
    <form
      class="recurrence-rule-editor"
      novalidate
      onSubmit={(event) => {
        event.preventDefault()
        requestConfirmation()
      }}
    >
      <header>
        <h3>
          {t(
            isEditing()
              ? 'recurring.rules.editor.editTitle'
              : 'recurring.rules.editor.createTitle',
          )}
        </h3>
      </header>

      <RecurrenceRuleFields
        form={form}
        isEditing={isEditing()}
        disabled={mutation.isPending}
        errors={apiError()?.fieldErrors}
        onChange={closeConfirmation}
      />

      <div class="recurrence-impact-note">
        <AlertTriangle size={16} strokeWidth={1.9} aria-hidden="true" />
        <p>
          {t(
            isEditing()
              ? 'recurring.rules.editor.updateImpact'
              : 'recurring.rules.editor.createImpact',
          )}
        </p>
      </div>

      <Show when={errorKey()}>
        {(key) => (
          <FormErrorSummary
            error={apiError()}
            message={t(
              apiError()?.code === 'request_validation_error'
                ? 'common.validation.summary'
                : key(),
            )}
            fieldLabels={recurrenceFieldLabels(t)}
          />
        )}
      </Show>

      <div class="recurrence-rule-editor-actions">
        <button
          type="button"
          disabled={mutation.isPending}
          onClick={() => props.onClose()}
        >
          {t('recurring.rules.actions.cancel')}
        </button>
        <button type="submit" class="primary-button" disabled={mutation.isPending}>
          {t('recurring.rules.actions.continue')}
        </button>
      </div>

      <Show when={isConfirmationOpen()}>
        <div class="recurrence-confirmation" role="alert">
          <div>
            <strong>
              {t(
                isEditing()
                  ? 'recurring.rules.editor.confirmUpdateTitle'
                  : 'recurring.rules.editor.confirmCreateTitle',
              )}
            </strong>
            <p>
              {t(
                isEditing()
                  ? 'recurring.rules.editor.updateImpact'
                  : 'recurring.rules.editor.createImpact',
              )}
            </p>
          </div>
          <div>
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={() => setConfirmationOpen(false)}
            >
              {t('recurring.rules.actions.cancel')}
            </button>
            <button
              type="button"
              class="recurrence-confirm-primary"
              disabled={mutation.isPending}
              aria-busy={mutation.isPending}
              onClick={() => void save()}
            >
              <Show when={mutation.isPending}>
                <LoaderCircle class="spin" size={14} strokeWidth={2} />
              </Show>
              {t(
                isEditing()
                  ? 'recurring.rules.actions.update'
                  : 'recurring.rules.actions.create',
              )}
            </button>
          </div>
        </div>
      </Show>
      <UnsavedChangesDialog controller={navigationGuard} />
    </form>
  )
}
