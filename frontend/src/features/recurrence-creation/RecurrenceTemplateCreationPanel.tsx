import { createMutation, useQueryClient } from '@tanstack/solid-query'
import AlertTriangle from 'lucide-solid/icons/triangle-alert'
import ArrowLeft from 'lucide-solid/icons/arrow-left'
import Check from 'lucide-solid/icons/check'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import { createMemo, createSignal, Show } from 'solid-js'

import './recurrence-template-creation.css'
import '@/features/task-form/task-form.css'
import '@/features/recurrence-mutations/recurrence-mutations.css'

import {
  createRecurrenceTemplate,
  type CreateRecurrenceTemplateInput,
} from '@/entities/recurrence/api'
import { addRecurrenceTemplateToCache } from '@/entities/recurrence/cache'
import type { RecurrenceTemplate } from '@/entities/recurrence/model'
import {
  recurrenceFieldLabels,
  RecurrenceRuleFields,
} from '@/features/recurrence-rules/RecurrenceRuleFields'
import { createRecurrenceRuleForm } from '@/features/recurrence-rules/recurrenceRuleForm'
import type { TaskPriority } from '@/entities/task/model'
import { invalidateTaskLists } from '@/entities/task/cache'
import { TaskDescriptionEditor } from '@/features/task-form/TaskDescriptionEditor'
import { TaskTagField } from '@/features/task-form/TaskTagField'
import {
  taskPriorities,
  taskPriorityLabelKeys,
} from '@/features/task-form/taskPriorities'
import { ApiError } from '@/shared/api/http'
import { type FormApiError, toFormApiError } from '@/shared/forms/apiErrors'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import {
  createUnsavedChangesGuard,
  UnsavedChangesDialog,
} from '@/shared/navigation/UnsavedChangesGuard'
import { SelectField } from '@/shared/ui/SelectField'
import { FormErrorSummary } from '@/shared/ui/FormErrorSummary'

export function RecurrenceTemplateCreationPanel(props: {
  onCancel: () => void
  onCreated: (template: RecurrenceTemplate) => void
}) {
  const queryClient = useQueryClient()
  const { t } = useI18n()
  const ruleForm = createRecurrenceRuleForm()
  const [title, setTitle] = createSignal('')
  const [description, setDescription] = createSignal('')
  const [priority, setPriority] = createSignal<TaskPriority>('normal')
  const [tagIds, setTagIds] = createSignal<readonly string[]>([])
  const [isTagOperationPending, setTagOperationPending] = createSignal(false)
  const [isConfirmationOpen, setConfirmationOpen] = createSignal(false)
  const [errorKey, setErrorKey] = createSignal<TranslationKey>()
  const [apiError, setApiError] = createSignal<FormApiError>()
  const hasUnsavedChanges = createMemo(
    () =>
      title().length > 0 ||
      description().length > 0 ||
      priority() !== 'normal' ||
      tagIds().length > 0 ||
      ruleForm.isDirty(),
  )
  // The guard reads this accessor from router and lifecycle callbacks.
  // eslint-disable-next-line solid/reactivity
  const navigationGuard = createUnsavedChangesGuard(hasUnsavedChanges)

  const creation = createMutation(() => ({
    mutationFn: (data: CreateRecurrenceTemplateInput) =>
      createRecurrenceTemplate(data),
    onSuccess: (template) => {
      addRecurrenceTemplateToCache(queryClient, template)
      void invalidateTaskLists(queryClient)
      navigationGuard.allowNextNavigation()
      props.onCreated(template)
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
    if (title().trim().length === 0) {
      setErrorKey('recurring.creation.titleRequired')
      return
    }
    if (!ruleForm.isValid()) {
      setErrorKey('recurring.creation.ruleInvalid')
      return
    }
    setConfirmationOpen(true)
  }

  const submit = async () => {
    const trimmedDescription = description().trim()
    const data: CreateRecurrenceTemplateInput = {
      title: title().trim(),
      priority: priority(),
      rules: [ruleForm.buildCreateInput()],
      ...(trimmedDescription.length > 0
        ? { description: trimmedDescription }
        : {}),
      ...(tagIds().length > 0 ? { tag_ids: tagIds() } : {}),
    }
    setErrorKey()
    setApiError()
    try {
      await creation.mutateAsync(data)
    } catch (error) {
      setApiError(
        toFormApiError(error, {
          fields: [
            'title',
            'description',
            'priority',
            'tag_ids',
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
          ? 'recurring.creation.overlap'
          : 'recurring.creation.mutationError',
      )
    }
  }

  const isPending = () => creation.isPending || isTagOperationPending()

  return (
    <section
      class="recurrence-template-creation"
      aria-labelledby="recurrence-template-creation-title"
    >
      <header class="recurrence-template-creation-header">
        <button
          type="button"
          disabled={isPending()}
          onClick={() => {
            navigationGuard.allowNextNavigation()
            props.onCancel()
          }}
        >
          <ArrowLeft size={17} strokeWidth={2} />
          {t('recurring.creation.cancel')}
        </button>
        <h1 id="recurrence-template-creation-title">
          {t('recurring.creation.title')}
        </h1>
      </header>

      <form
        class="task-form recurrence-template-creation-form"
        novalidate
        onSubmit={(event) => {
          event.preventDefault()
          requestConfirmation()
        }}
      >
        <label>
          <span>{t('recurring.creation.name')}</span>
          <input
            class="task-form-title-input"
            name="title"
            value={title()}
            maxlength={250}
            required
            autofocus
            disabled={isPending()}
            aria-invalid={apiError()?.fieldErrors.title !== undefined}
            aria-describedby={
              apiError()?.fieldErrors.title === undefined
                ? undefined
                : 'recurrence-creation-title-error'
            }
            onInput={(event) => {
              setTitle(event.currentTarget.value)
              closeConfirmation()
            }}
          />
          <Show when={apiError()?.fieldErrors.title}>
            {(error) => (
              <small id="recurrence-creation-title-error" class="task-field-error">
                {error()}
              </small>
            )}
          </Show>
        </label>

        <TaskDescriptionEditor
          value={description()}
          disabled={isPending()}
          error={apiError()?.fieldErrors.description}
          onChange={(value) => {
            setDescription(value)
            closeConfirmation()
          }}
        />

        <SelectField
          name="priority"
          label={t('recurring.creation.priority')}
          value={priority()}
          disabled={isPending()}
          error={apiError()?.fieldErrors.priority}
          options={taskPriorities.map((value) => ({
            label: t(taskPriorityLabelKeys[value]),
            value,
          }))}
          onChange={(value) => {
            setPriority(value)
            closeConfirmation()
          }}
        />

        <TaskTagField
          id="recurrence-template-creation-tags"
          selectedTagIds={tagIds()}
          disabled={creation.isPending}
          onChange={(value) => {
            setTagIds(value)
            closeConfirmation()
          }}
          onPendingChange={setTagOperationPending}
        />

        <section
          class="recurrence-template-rule-section"
          aria-labelledby="recurrence-template-first-rule-title"
        >
          <div>
            <h2 id="recurrence-template-first-rule-title">
              {t('recurring.creation.firstRule')}
            </h2>
            <p>{t('recurring.creation.firstRuleDescription')}</p>
          </div>

          <RecurrenceRuleFields
            form={ruleForm}
            isEditing={false}
            disabled={isPending()}
            errors={apiError()?.fieldErrors}
            onChange={closeConfirmation}
          />
        </section>

        <div class="recurrence-impact-note">
          <AlertTriangle size={16} strokeWidth={1.9} aria-hidden="true" />
          <p>{t('recurring.creation.impact')}</p>
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

        <div class="recurrence-template-creation-actions">
          <button
            type="button"
            disabled={isPending()}
            onClick={() => {
              navigationGuard.allowNextNavigation()
              props.onCancel()
            }}
          >
            {t('recurring.creation.cancel')}
          </button>
          <button type="submit" class="primary-button" disabled={isPending()}>
            {t('recurring.creation.review')}
          </button>
        </div>

        <Show when={isConfirmationOpen()}>
          <div class="recurrence-confirmation" role="alert">
            <div>
              <strong>{t('recurring.creation.confirmTitle')}</strong>
              <p>{t('recurring.creation.confirmMessage')}</p>
            </div>
            <div>
              <button
                type="button"
                disabled={isPending()}
                onClick={() => setConfirmationOpen(false)}
              >
                {t('recurring.creation.cancel')}
              </button>
              <button
                type="button"
                class="recurrence-confirm-primary"
                disabled={isPending()}
                aria-busy={creation.isPending}
                onClick={() => void submit()}
              >
                <Show
                  when={creation.isPending}
                  fallback={<Check size={14} strokeWidth={2} />}
                >
                  <LoaderCircle class="spin" size={14} strokeWidth={2} />
                </Show>
                {t(
                  creation.isPending
                    ? 'recurring.creation.creating'
                    : 'recurring.creation.create',
                )}
              </button>
            </div>
          </div>
        </Show>
      </form>
      <UnsavedChangesDialog controller={navigationGuard} />
    </section>
  )
}
