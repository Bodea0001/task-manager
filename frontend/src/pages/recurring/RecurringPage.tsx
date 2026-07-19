import { createMutation, createQuery, useQueryClient } from '@tanstack/solid-query'
import { useSearchParams } from '@solidjs/router'
import AlertCircle from 'lucide-solid/icons/circle-alert'
import ArrowLeft from 'lucide-solid/icons/arrow-left'
import CalendarClock from 'lucide-solid/icons/calendar-clock'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import Pencil from 'lucide-solid/icons/pencil'
import Plus from 'lucide-solid/icons/plus'
import Repeat2 from 'lucide-solid/icons/repeat-2'
import Search from 'lucide-solid/icons/search'
import Trash2 from 'lucide-solid/icons/trash-2'
import X from 'lucide-solid/icons/x'
import {
  createEffect,
  createMemo,
  createSignal,
  For,
  lazy,
  Match,
  Show,
  Suspense,
  Switch,
} from 'solid-js'

import './recurring.css'

import {
  deleteRecurrenceRule,
  deleteRecurrenceTemplate,
  getRecurrenceTemplate,
  listRecurrenceTemplates,
  RECURRENCE_TEMPLATES_QUERY_KEY,
  recurrenceTemplateQueryKey,
} from '@/entities/recurrence/api'
import type {
  RecurrenceBusinessDayPolicy,
  RecurrenceFrequency,
  RecurrenceRule,
  RecurrenceTemplate,
  Weekday,
} from '@/entities/recurrence/model'
import { invalidateTaskLists } from '@/entities/task/cache'
import type { TaskPriority } from '@/entities/task/model'
import {
  removeRecurrenceRuleFromCache,
  removeRecurrenceTemplateFromCache,
} from '@/entities/recurrence/cache'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import { MarkdownContent } from '@/shared/ui/MarkdownContent'

const LazyRecurrenceTemplateCreationPanel = lazy(async () => ({
  default: (
    await import(
      '@/features/recurrence-creation/RecurrenceTemplateCreationPanel'
    )
  ).RecurrenceTemplateCreationPanel,
}))
const LazyRecurrenceOccurrenceManager = lazy(async () => ({
  default: (
    await import(
      '@/features/recurrence-occurrences/RecurrenceOccurrenceManager'
    )
  ).RecurrenceOccurrenceManager,
}))
const LazyRecurrenceRuleEditor = lazy(async () => ({
  default: (
    await import('@/features/recurrence-rules/RecurrenceRuleEditor')
  ).RecurrenceRuleEditor,
}))
const LazyRecurrenceTagManager = lazy(async () => ({
  default: (
    await import('@/features/recurrence-tags/RecurrenceTagManager')
  ).RecurrenceTagManager,
}))

const priorityLabelKeys: Record<TaskPriority, TranslationKey> = {
  low: 'recurring.priority.low',
  normal: 'recurring.priority.normal',
  high: 'recurring.priority.high',
  urgent: 'recurring.priority.urgent',
}

const frequencyLabelKeys: Record<RecurrenceFrequency, TranslationKey> = {
  daily: 'recurring.rules.frequency.daily',
  weekly: 'recurring.rules.frequency.weekly',
  monthly: 'recurring.rules.frequency.monthly',
}

const intervalLabelKeys: Record<RecurrenceFrequency, TranslationKey> = {
  daily: 'recurring.rules.interval_daily',
  weekly: 'recurring.rules.interval_weekly',
  monthly: 'recurring.rules.interval_monthly',
}

const weekdayLabelKeys: Record<Weekday, TranslationKey> = {
  1: 'recurring.rules.weekdays.monday',
  2: 'recurring.rules.weekdays.tuesday',
  3: 'recurring.rules.weekdays.wednesday',
  4: 'recurring.rules.weekdays.thursday',
  5: 'recurring.rules.weekdays.friday',
  6: 'recurring.rules.weekdays.saturday',
  7: 'recurring.rules.weekdays.sunday',
}

const businessDayPolicyLabelKeys: Record<
  RecurrenceBusinessDayPolicy,
  TranslationKey
> = {
  none: 'recurring.rules.editor.businessDay.none',
  next_business_day: 'recurring.rules.editor.businessDay.next',
  previous_business_day: 'recurring.rules.editor.businessDay.previous',
}

export function RecurringPage(props: { emailVerified: boolean }) {
  const queryClient = useQueryClient()
  const { formatDateTime, t } = useI18n()
  const [searchParams, setSearchParams] = useSearchParams<{
    create?: string
    template?: string
  }>()
  const [searchText, setSearchText] = createSignal('')
  let recurringTitle: HTMLHeadingElement | undefined
  const templatesQuery = createQuery(() => ({
    queryKey: RECURRENCE_TEMPLATES_QUERY_KEY,
    queryFn: listRecurrenceTemplates,
  }))
  const isCreating = () => searchParams.create === '1'
  const selectedTemplateId = () => searchParams.template || undefined
  const filteredTemplates = createMemo(() => {
    const query = searchText().trim().toLocaleLowerCase()
    if (query.length === 0) {
      return templatesQuery.data?.templates || []
    }
    return (templatesQuery.data?.templates || []).filter((template) =>
      [
        template.title,
        template.description || '',
        ...template.tags.map((tag) => tag.name),
      ].some((value) => value.toLocaleLowerCase().includes(query)),
    )
  })

  const openTemplate = (template: RecurrenceTemplate) => {
    queryClient.setQueryData(
      recurrenceTemplateQueryKey(template.template_id),
      template,
    )
    setSearchParams({ create: undefined, template: template.template_id })
  }

  const openCreation = () => {
    if (!props.emailVerified) return
    setSearchParams({ create: '1', template: undefined })
  }

  const closeCreation = () => {
    setSearchParams({ create: undefined }, { replace: true })
    queueMicrotask(() => recurringTitle?.focus())
  }

  const closeDetails = () => {
    setSearchParams({ template: undefined })
    queueMicrotask(() => recurringTitle?.focus())
  }

  createEffect(() => {
    if (!props.emailVerified && isCreating()) {
      setSearchParams({ create: undefined }, { replace: true })
    }
  })

  return (
    <section class="recurring-page" aria-label={t('recurring.title')}>
      <Show when={!props.emailVerified}>
        <div class="recurring-access-notice" role="status">
          <AlertCircle size={17} strokeWidth={1.9} aria-hidden="true" />
          <div>
            <strong>{t('recurring.access.title')}</strong>
            <span>{t('recurring.access.message')}</span>
          </div>
        </div>
      </Show>

      <Show when={isCreating() && props.emailVerified}>
        <Suspense
          fallback={
            <RecurringLazyState
              label={t('recurring.states.loading')}
              spacious
            />
          }
        >
          <LazyRecurrenceTemplateCreationPanel
            onCancel={closeCreation}
            onCreated={(template) => {
              setSearchParams(
                { create: undefined, template: template.template_id },
                { replace: true },
              )
            }}
          />
        </Suspense>
      </Show>

      <Show when={!isCreating() && selectedTemplateId() === undefined}>
        <header class="recurring-header">
          <div>
            <h1
              ref={(element) => {
                recurringTitle = element
              }}
              tabIndex={-1}
            >
              {t('recurring.title')}
            </h1>
            <p>{t('recurring.description')}</p>
          </div>
          <Show when={(templatesQuery.data?.templates.length || 0) > 0}>
            <button
              type="button"
              disabled={!props.emailVerified}
              title={
                props.emailVerified ? undefined : t('recurring.access.actionHint')
              }
              onClick={openCreation}
            >
              <Plus size={15} strokeWidth={2.1} />
              {t('recurring.creation.action')}
            </button>
          </Show>
        </header>

        <div class="recurring-toolbar">
          <div class="recurring-search">
            <Search size={17} strokeWidth={1.9} aria-hidden="true" />
            <label class="visually-hidden" for="recurring-search-input">
              {t('recurring.search.label')}
            </label>
            <input
              id="recurring-search-input"
              type="search"
              value={searchText()}
              placeholder={t('recurring.search.placeholder')}
              onInput={(event) => setSearchText(event.currentTarget.value)}
            />
            <Show when={searchText().length > 0}>
              <button
                type="button"
                aria-label={t('recurring.search.clear')}
                title={t('recurring.search.clear')}
                onClick={() => setSearchText('')}
              >
                <X size={15} strokeWidth={1.9} />
              </button>
            </Show>
          </div>
        </div>

        <Switch>
          <Match when={templatesQuery.isPending}>
            <RecurringListSkeleton />
          </Match>
          <Match when={templatesQuery.isError}>
            <RecurringErrorState onRetry={() => void templatesQuery.refetch()} />
          </Match>
          <Match when={filteredTemplates().length === 0}>
            <RecurringEmptyState
              hasSearch={searchText().trim().length > 0}
              canCreate={props.emailVerified}
              onCreate={openCreation}
            />
          </Match>
          <Match when={filteredTemplates().length > 0}>
            <div class="recurring-list">
              <For each={filteredTemplates()}>
                {(template) => (
                  <button
                    type="button"
                    class="recurring-row"
                    aria-label={t('recurring.list.open', { title: template.title })}
                    onClick={() => openTemplate(template)}
                  >
                    <span class="recurring-row-icon" aria-hidden="true">
                      <Repeat2 size={18} strokeWidth={1.9} />
                    </span>
                    <span class="recurring-row-content">
                      <strong>{template.title}</strong>
                      <span>
                        {t('recurring.list.ruleCount', {
                          count: template.rules.length,
                        })}
                        {' · '}
                        {t(priorityLabelKeys[template.priority])}
                      </span>
                    </span>
                    <span class="recurring-row-meta">
                      <Show when={template.tags.length > 0}>
                        <span class="recurring-row-tags">
                          <For each={template.tags.slice(0, 2)}>
                            {(tag) => <span>{tag.name}</span>}
                          </For>
                        </span>
                      </Show>
                      <time datetime={template.created_at}>
                        {t('recurring.list.created', {
                          date: formatDateTime(new Date(template.created_at), {
                            dateStyle: 'medium',
                          }),
                        })}
                      </time>
                    </span>
                  </button>
                )}
              </For>
            </div>
          </Match>
        </Switch>
      </Show>

      <Show when={!isCreating() && selectedTemplateId()}>
        {(templateId) => (
          <RecurringDetails
            emailVerified={props.emailVerified}
            templateId={templateId()}
            onClose={closeDetails}
            onDeleted={closeDetails}
          />
        )}
      </Show>
    </section>
  )
}

type PendingDeletion =
  | { kind: 'rule'; rule: RecurrenceRule }
  | { kind: 'template' }

function RecurringDetails(props: {
  emailVerified: boolean
  templateId: string
  onClose: () => void
  onDeleted: () => void
}) {
  const queryClient = useQueryClient()
  const { formatDateTime, t } = useI18n()
  const [editedRuleId, setEditedRuleId] = createSignal<string>()
  const [pendingDeletion, setPendingDeletion] = createSignal<PendingDeletion>()
  const [deletionErrorKey, setDeletionErrorKey] = createSignal<TranslationKey>()
  let titleHeading: HTMLHeadingElement | undefined
  let hasFocusedTitle = false
  const templateQuery = createQuery(() => ({
    queryKey: recurrenceTemplateQueryKey(props.templateId),
    queryFn: () => getRecurrenceTemplate(props.templateId),
    staleTime: 30_000,
  }))
  const templateDeletion = createMutation(() => ({
    mutationFn: () => deleteRecurrenceTemplate(props.templateId),
    onSuccess: () => {
      removeRecurrenceTemplateFromCache(queryClient, props.templateId)
      void invalidateTaskLists(queryClient)
      props.onDeleted()
    },
  }))
  const ruleDeletion = createMutation(() => ({
    mutationFn: (rule: RecurrenceRule) =>
      deleteRecurrenceRule(rule.recurrence_id),
    onSuccess: (_, rule) => {
      setPendingDeletion()
      removeRecurrenceRuleFromCache(
        queryClient,
        rule.template_id,
        rule.recurrence_id,
      )
      void invalidateTaskLists(queryClient)
    },
  }))
  const isDeletionPending = () =>
    templateDeletion.isPending || ruleDeletion.isPending

  createEffect(() => {
    if (templateQuery.data === undefined || hasFocusedTitle) return
    hasFocusedTitle = true
    queueMicrotask(() => titleHeading?.focus())
  })

  const requestDeletion = (deletion: PendingDeletion) => {
    setDeletionErrorKey()
    setEditedRuleId()
    setPendingDeletion(deletion)
  }

  const confirmDeletion = async () => {
    const deletion = pendingDeletion()
    if (deletion === undefined) return
    setDeletionErrorKey()
    try {
      if (deletion.kind === 'template') {
        await templateDeletion.mutateAsync()
      } else {
        await ruleDeletion.mutateAsync(deletion.rule)
      }
    } catch {
      setDeletionErrorKey(
        deletion.kind === 'template'
          ? 'recurring.details.deleteError'
          : 'recurring.rules.deletion.error',
      )
    }
  }

  return (
    <div class="recurring-details">
      <button type="button" class="recurring-back" onClick={() => props.onClose()}>
        <ArrowLeft size={17} strokeWidth={2} />
        {t('recurring.details.back')}
      </button>
      <Switch>
        <Match when={templateQuery.isPending}>
          <div class="recurring-state" aria-label={t('recurring.states.loading')}>
            <LoaderCircle class="spin" size={24} strokeWidth={1.8} />
          </div>
        </Match>
        <Match when={templateQuery.isError}>
          <div class="recurring-state" role="alert">
            <AlertCircle size={24} strokeWidth={1.8} />
            <h2>{t('recurring.states.detailsErrorTitle')}</h2>
            <p>{t('recurring.states.detailsErrorMessage')}</p>
            <button type="button" onClick={() => void templateQuery.refetch()}>
              {t('recurring.states.retry')}
            </button>
          </div>
        </Match>
        <Match when={templateQuery.data !== undefined}>
          <Show keyed when={templateQuery.data}>
            {(template) => (
              <>
                <header class="recurring-details-header">
                  <div>
                    <h1
                      ref={(element) => {
                        titleHeading = element
                      }}
                      tabIndex={-1}
                    >
                      {template.title}
                    </h1>
                    <span class={`recurring-priority recurring-priority--${template.priority}`}>
                      {t(priorityLabelKeys[template.priority])}
                    </span>
                  </div>
                  <div class="recurring-details-meta">
                    <time datetime={template.created_at}>
                      {t('recurring.list.created', {
                        date: formatDateTime(new Date(template.created_at), {
                          dateStyle: 'medium',
                        }),
                      })}
                    </time>
                    <button
                      type="button"
                      disabled={isDeletionPending()}
                      onClick={() => requestDeletion({ kind: 'template' })}
                    >
                      <Trash2 size={14} strokeWidth={1.9} />
                      {t('recurring.details.delete')}
                    </button>
                  </div>
                </header>

                <section class="recurring-details-section">
                  <h2>{t('recurring.details.description')}</h2>
                  <Show
                    when={template.description}
                    fallback={<p class="recurring-muted">{t('recurring.details.noDescription')}</p>}
                  >
                    {(description) => <MarkdownContent source={description()} />}
                  </Show>
                </section>

                <section class="recurring-details-section">
                  <h2>{t('recurring.occurrences.title')}</h2>
                  <Suspense
                    fallback={
                      <RecurringLazyState
                        label={t('recurring.occurrences.loading')}
                      />
                    }
                  >
                    <LazyRecurrenceOccurrenceManager template={template} />
                  </Suspense>
                </section>

                <section class="recurring-details-section">
                  <div class="recurring-section-heading">
                    <h2>{t('recurring.details.rules')}</h2>
                    <button
                      type="button"
                      disabled={!props.emailVerified}
                      title={
                        props.emailVerified
                          ? undefined
                          : t('recurring.access.actionHint')
                      }
                      onClick={() => setEditedRuleId('new')}
                    >
                      <Plus size={14} strokeWidth={2.1} />
                      {t('recurring.rules.actions.add')}
                    </button>
                  </div>
                  <div class="recurring-rules">
                    <For each={template.rules}>
                      {(rule) => (
                        <RecurrenceRuleItem
                          rule={rule}
                          disabled={isDeletionPending()}
                          canEdit={props.emailVerified}
                          onEdit={() => setEditedRuleId(rule.recurrence_id)}
                          onDelete={() => requestDeletion({ kind: 'rule', rule })}
                        />
                      )}
                    </For>
                  </div>
                  <Show when={template.rules.length === 0}>
                    <p class="recurring-muted">{t('recurring.states.noRules')}</p>
                  </Show>
                  <Show keyed when={editedRuleId()}>
                    {(ruleId) => (
                      <Suspense
                        fallback={
                          <RecurringLazyState
                            label={t('recurring.states.loading')}
                          />
                        }
                      >
                        <LazyRecurrenceRuleEditor
                          templateId={template.template_id}
                          rule={
                            ruleId === 'new'
                              ? undefined
                              : template.rules.find(
                                  (rule) => rule.recurrence_id === ruleId,
                                )
                          }
                          onClose={() => setEditedRuleId()}
                        />
                      </Suspense>
                    )}
                  </Show>
                  <Show when={pendingDeletion()?.kind === 'rule'}>
                    <RecurrenceDeletionConfirmation
                      kind="rule"
                      isPending={isDeletionPending()}
                      errorKey={deletionErrorKey()}
                      onCancel={() => {
                        setPendingDeletion()
                        setDeletionErrorKey()
                      }}
                      onConfirm={() => void confirmDeletion()}
                    />
                  </Show>
                </section>

                <section class="recurring-details-section">
                  <h2>{t('recurring.details.manageTags')}</h2>
                  <Suspense
                    fallback={
                      <RecurringLazyState label={t('recurring.tags.loading')} />
                    }
                  >
                    <LazyRecurrenceTagManager template={template} />
                  </Suspense>
                </section>

                <Show when={pendingDeletion()?.kind === 'template'}>
                  <RecurrenceDeletionConfirmation
                    kind="template"
                    isPending={isDeletionPending()}
                    errorKey={deletionErrorKey()}
                    onCancel={() => {
                      setPendingDeletion()
                      setDeletionErrorKey()
                    }}
                    onConfirm={() => void confirmDeletion()}
                  />
                </Show>
              </>
            )}
          </Show>
        </Match>
      </Switch>
    </div>
  )
}

function RecurrenceRuleItem(props: {
  canEdit: boolean
  disabled: boolean
  onDelete: () => void
  onEdit: () => void
  rule: RecurrenceRule
}) {
  const { formatDateTime, t } = useI18n()
  const firstOccurrenceLabel = () =>
    t('recurring.rules.firstOccurrence', {
      date: formatDateTime(new Date(`${props.rule.anchor_date}T00:00`), {
        dateStyle: 'medium',
      }),
    })
  const timingLabel = () => {
    const startsAt = new Date(
      `${props.rule.anchor_date}T${props.rule.default_time.slice(0, 5)}`,
    )
    if (props.rule.schedule === null) {
      return t('recurring.rules.deadlineTime', {
        time: formatDateTime(startsAt, { timeStyle: 'short' }),
      })
    }
    const endsAt = new Date(props.rule.schedule.ends_at)
    return t('recurring.rules.scheduledTime', {
      start: formatDateTime(startsAt, { timeStyle: 'short' }),
      end: formatDateTime(
        endsAt,
        startsAt.toDateString() === endsAt.toDateString()
          ? { timeStyle: 'short' }
          : { dateStyle: 'medium', timeStyle: 'short' },
      ),
    })
  }
  const patternLabel = () => {
    if (props.rule.frequency === 'weekly') {
      return props.rule.weekdays
        .map((weekday) => t(weekdayLabelKeys[weekday]))
        .join(', ')
    }
    if (props.rule.frequency === 'monthly' && props.rule.month_rule !== null) {
      const monthRule = props.rule.month_rule
      if (monthRule.month_day !== null) {
        return t('recurring.rules.monthRule.monthDay', { day: monthRule.month_day })
      }
      return t('recurring.rules.monthRule.ordinalWeekday', {
        position: t(
          `recurring.rules.editor.ordinal.${monthRule.week_of_month === -1 ? 'last' : `week${monthRule.week_of_month}`}` as TranslationKey,
        ),
        weekday:
          monthRule.weekday === null ? '' : t(weekdayLabelKeys[monthRule.weekday]),
      })
    }
    return undefined
  }
  const endLabel = () => {
    if (props.rule.repeat_until !== null) {
      return t('recurring.rules.endsOn', {
        date: formatDateTime(new Date(`${props.rule.repeat_until}T00:00`), {
          dateStyle: 'medium',
        }),
      })
    }
    if (props.rule.occurrences_limit !== null) {
      return t('recurring.rules.occurrenceLimit', {
        count: props.rule.occurrences_limit,
      })
    }
    return t('recurring.rules.noEnd')
  }

  return (
    <article class="recurring-rule">
      <span class="recurring-rule-icon" aria-hidden="true">
        <CalendarClock size={18} strokeWidth={1.8} />
      </span>
      <div>
        <strong>{t(frequencyLabelKeys[props.rule.frequency])}</strong>
        <p>
          {t(intervalLabelKeys[props.rule.frequency], {
            count: props.rule.interval,
          })}
        </p>
        <Show when={patternLabel()}>{(label) => <span>{label()}</span>}</Show>
        <time>{firstOccurrenceLabel()}</time>
        <span>{timingLabel()}</span>
        <Show
          when={
            props.rule.month_rule !== null &&
            props.rule.month_rule.business_day_policy !== 'none'
              ? props.rule.month_rule.business_day_policy
              : undefined
          }
        >
          {(policy) => (
            <span>
              {t('recurring.rules.businessDayAdjustment', {
                policy: t(businessDayPolicyLabelKeys[policy()]),
              })}
            </span>
          )}
        </Show>
        <span>{endLabel()}</span>
      </div>
      <div class="recurring-rule-actions">
        <button
          type="button"
          disabled={props.disabled || !props.canEdit}
          aria-label={t('recurring.rules.actions.editNamed', {
            name: t(frequencyLabelKeys[props.rule.frequency]),
          })}
          title={
            props.canEdit
              ? t('recurring.rules.actions.edit')
              : t('recurring.access.actionHint')
          }
          onClick={() => props.onEdit()}
        >
          <Pencil size={14} strokeWidth={1.9} />
        </button>
        <button
          type="button"
          class="recurring-rule-delete"
          disabled={props.disabled}
          aria-label={t('recurring.rules.actions.deleteNamed', {
            name: t(frequencyLabelKeys[props.rule.frequency]),
          })}
          title={t('recurring.rules.actions.delete')}
          onClick={() => props.onDelete()}
        >
          <Trash2 size={14} strokeWidth={1.9} />
        </button>
      </div>
    </article>
  )
}

function RecurrenceDeletionConfirmation(props: {
  errorKey?: TranslationKey
  isPending: boolean
  kind: 'rule' | 'template'
  onCancel: () => void
  onConfirm: () => void
}) {
  const { t } = useI18n()
  const isTemplate = () => props.kind === 'template'
  return (
    <div class="recurrence-deletion-block">
      <div class="recurrence-confirmation" role="alert">
        <div>
          <strong>
            {t(
              isTemplate()
                ? 'recurring.details.deleteTitle'
                : 'recurring.rules.deletion.title',
            )}
          </strong>
          <p>
            {t(
              isTemplate()
                ? 'recurring.details.deleteMessage'
                : 'recurring.rules.deletion.message',
            )}
          </p>
        </div>
        <div>
          <button
            type="button"
            disabled={props.isPending}
            onClick={() => props.onCancel()}
          >
            {t('recurring.rules.actions.cancel')}
          </button>
          <button
            type="button"
            class="recurrence-confirm-danger"
            disabled={props.isPending}
            aria-busy={props.isPending}
            onClick={() => props.onConfirm()}
          >
            <Show when={props.isPending}>
              <LoaderCircle class="spin" size={14} strokeWidth={2} />
            </Show>
            {t(
              isTemplate()
                ? 'recurring.details.confirmDelete'
                : 'recurring.rules.actions.confirmDelete',
            )}
          </button>
        </div>
      </div>
      <Show when={props.errorKey}>
        {(key) => (
          <p class="recurrence-form-error" role="alert">
            {t(key())}
          </p>
        )}
      </Show>
    </div>
  )
}

function RecurringErrorState(props: { onRetry: () => void }) {
  const { t } = useI18n()
  return (
    <div class="recurring-state" role="alert">
      <AlertCircle size={24} strokeWidth={1.8} />
      <h2>{t('recurring.states.loadErrorTitle')}</h2>
      <p>{t('recurring.states.loadErrorMessage')}</p>
      <button type="button" onClick={() => props.onRetry()}>
        {t('recurring.states.retry')}
      </button>
    </div>
  )
}

function RecurringEmptyState(props: {
  canCreate: boolean
  hasSearch: boolean
  onCreate: () => void
}) {
  const { t } = useI18n()
  return (
    <div class="recurring-state">
      <Repeat2 size={24} strokeWidth={1.8} />
      <h2>
        {t(
          props.hasSearch
            ? 'recurring.states.noMatchesTitle'
            : 'recurring.states.emptyTitle',
        )}
      </h2>
      <p>
        {t(
          props.hasSearch
            ? 'recurring.states.noMatchesMessage'
            : 'recurring.states.emptyMessage',
        )}
      </p>
      <Show when={!props.hasSearch}>
        <button
          type="button"
          disabled={!props.canCreate}
          title={
            props.canCreate ? undefined : t('recurring.access.actionHint')
          }
          onClick={() => props.onCreate()}
        >
          <Plus size={14} strokeWidth={2.1} />
          {t('recurring.creation.action')}
        </button>
      </Show>
    </div>
  )
}

function RecurringListSkeleton() {
  const { t } = useI18n()
  return (
    <div class="recurring-skeleton" aria-label={t('recurring.states.loading')}>
      <For each={Array.from({ length: 4 })}>
        {() => (
          <span>
            <i />
            <i />
          </span>
        )}
      </For>
    </div>
  )
}

function RecurringLazyState(props: { label: string; spacious?: boolean }) {
  return (
    <div
      class="recurring-lazy-state"
      classList={{ 'recurring-lazy-state--spacious': props.spacious }}
      role="status"
      aria-label={props.label}
    >
      <LoaderCircle class="spin" size={22} strokeWidth={1.8} />
      <span>{props.label}</span>
    </div>
  )
}
