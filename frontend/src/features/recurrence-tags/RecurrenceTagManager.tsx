import { createMutation, createQuery, useQueryClient } from '@tanstack/solid-query'
import AlertTriangle from 'lucide-solid/icons/triangle-alert'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import Plus from 'lucide-solid/icons/plus'
import X from 'lucide-solid/icons/x'
import { createMemo, createSignal, For, Match, Show, Switch } from 'solid-js'

import './recurrence-tag-manager.css'
import '@/features/recurrence-mutations/recurrence-mutations.css'

import {
  addTagToRecurrenceTemplate,
  removeTagFromRecurrenceTemplate,
} from '@/entities/recurrence/api'
import { storeRecurrenceTemplate } from '@/entities/recurrence/cache'
import type { RecurrenceTemplate } from '@/entities/recurrence/model'
import { createTag, listTags, TAGS_QUERY_KEY } from '@/entities/tag/api'
import { addTagToCache } from '@/entities/tag/cache'
import { invalidateTaskLists } from '@/entities/task/cache'
import type { Tag } from '@/entities/tag/model'
import {
  clearFormApiField,
  type FormApiError,
  toFormApiError,
} from '@/shared/forms/apiErrors'
import { useI18n } from '@/shared/i18n/I18nProvider'
import { FormErrorSummary } from '@/shared/ui/FormErrorSummary'

type PendingTagChange =
  | { action: 'add' | 'remove'; tag: Tag }
  | { action: 'create'; name: string }

export function RecurrenceTagManager(props: { template: RecurrenceTemplate }) {
  const queryClient = useQueryClient()
  const { t } = useI18n()
  const [tagName, setTagName] = createSignal('')
  const [pendingChange, setPendingChange] = createSignal<PendingTagChange>()
  const [hasMutationError, setMutationError] = createSignal(false)
  const [apiError, setApiError] = createSignal<FormApiError>()
  const tagsQuery = createQuery(() => ({
    queryKey: TAGS_QUERY_KEY,
    queryFn: listTags,
    staleTime: 30_000,
  }))
  const selectedTagIds = () =>
    new Set(props.template.tags.map((tag) => tag.tag_id))
  const tags = () => tagsQuery.data?.tags || []
  const availableTags = createMemo(() =>
    tags().filter((tag) => !selectedTagIds().has(tag.tag_id)),
  )
  const normalizedTagName = () => normalizeTagName(tagName())
  const matchingTag = () =>
    tags().find((tag) => normalizeTagName(tag.name) === normalizedTagName())
  const cannotSubmitTag = () => {
    const match = matchingTag()
    return (
      isPending() ||
      normalizedTagName().length === 0 ||
      (match !== undefined && selectedTagIds().has(match.tag_id))
    )
  }
  const creation = createMutation(() => ({
    mutationFn: createTag,
    onSuccess: (tag) => addTagToCache(queryClient, tag),
  }))
  const mutation = createMutation(() => ({
    mutationFn: (change: Exclude<PendingTagChange, { action: 'create' }>) =>
      change.action === 'add'
        ? addTagToRecurrenceTemplate(props.template.template_id, change.tag.tag_id)
        : removeTagFromRecurrenceTemplate(
            props.template.template_id,
            change.tag.tag_id,
          ),
    onSuccess: (template) => {
      storeRecurrenceTemplate(queryClient, template)
      void invalidateTaskLists(queryClient)
      setPendingChange()
    },
  }))
  const isPending = () => creation.isPending || mutation.isPending

  const proposeChange = (change: PendingTagChange) => {
    setMutationError(false)
    setApiError()
    setPendingChange(change)
  }

  const proposeTagFromInput = () => {
    if (cannotSubmitTag()) return
    const match = matchingTag()
    proposeChange(
      match === undefined
        ? { action: 'create', name: tagName().trim() }
        : { action: 'add', tag: match },
    )
  }

  const confirmChange = async () => {
    const change = pendingChange()
    if (change === undefined || isPending()) {
      return
    }
    setMutationError(false)
    setApiError()
    try {
      const assignableChange =
        change.action === 'create'
          ? { action: 'add' as const, tag: await creation.mutateAsync(change.name) }
          : change
      if (change.action === 'create') {
        setPendingChange(assignableChange)
      }
      await mutation.mutateAsync(assignableChange)
      setTagName('')
    } catch (error) {
      setApiError(
        toFormApiError(error, {
          fields: change.action === 'create' ? ['name'] : [],
        }),
      )
      setMutationError(true)
    }
  }

  return (
    <div class="recurrence-tag-manager">
      <div class="recurrence-impact-note">
        <AlertTriangle size={16} strokeWidth={1.9} aria-hidden="true" />
        <p>{t('recurring.tags.impact')}</p>
      </div>

      <Show when={props.template.tags.length > 0}>
        <div class="recurrence-tag-options">
          <For each={props.template.tags}>
            {(tag) => (
              <button
                type="button"
                class="recurrence-tag-option recurrence-tag-option--selected"
                aria-label={t('recurring.tags.remove', { name: tag.name })}
                disabled={isPending()}
                onClick={() => proposeChange({ action: 'remove', tag })}
              >
                <X size={13} strokeWidth={2.2} aria-hidden="true" />
                {tag.name}
              </button>
            )}
          </For>
        </div>
      </Show>

      <div class="recurrence-tag-available">
        <strong>{t('recurring.tags.available')}</strong>
        <Switch>
          <Match when={tagsQuery.isPending}>
            <span class="recurrence-tag-state">
              <LoaderCircle class="spin" size={14} strokeWidth={2} />
              {t('recurring.tags.loading')}
            </span>
          </Match>
          <Match when={tagsQuery.isError}>
            <p class="recurrence-form-error" role="alert">
              {t('recurring.tags.loadError')}
            </p>
          </Match>
          <Match when={availableTags().length === 0}>
            <p class="recurrence-tag-state">{t('recurring.tags.noAvailable')}</p>
          </Match>
          <Match when={availableTags().length > 0}>
            <div class="recurrence-tag-options">
              <For each={availableTags()}>
                {(tag) => (
                  <button
                    type="button"
                    class="recurrence-tag-option"
                    aria-label={t('recurring.tags.add', { name: tag.name })}
                    disabled={isPending()}
                    onClick={() => proposeChange({ action: 'add', tag })}
                  >
                    <Plus size={13} strokeWidth={2.2} aria-hidden="true" />
                    {tag.name}
                  </button>
                )}
              </For>
            </div>
          </Match>
        </Switch>
      </div>

      <div class="recurrence-tag-create-row">
        <label class="visually-hidden" for="recurrence-tag-input">
          {t('recurring.tags.inputLabel')}
        </label>
        <input
          id="recurrence-tag-input"
          value={tagName()}
          maxlength={100}
          disabled={isPending()}
          placeholder={t('recurring.tags.placeholder')}
          aria-invalid={apiError()?.fieldErrors.name !== undefined}
          aria-describedby={
            apiError()?.fieldErrors.name === undefined
              ? undefined
              : 'recurrence-tag-input-error'
          }
          onInput={(event) => {
            setTagName(event.currentTarget.value)
            setMutationError(false)
            setApiError((current) => clearFormApiField(current, 'name'))
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              proposeTagFromInput()
            }
          }}
        />
        <button
          type="button"
          disabled={cannotSubmitTag()}
          onClick={proposeTagFromInput}
        >
          <Plus size={14} strokeWidth={2.1} aria-hidden="true" />
          {t(
            matchingTag() === undefined
              ? 'recurring.tags.create'
              : 'recurring.tags.select',
          )}
        </button>
      </div>

      <Show when={apiError()?.fieldErrors.name}>
        {(error) => (
          <small id="recurrence-tag-input-error" class="recurrence-form-error">
            {error()}
          </small>
        )}
      </Show>

      <Show when={hasMutationError()}>
        <FormErrorSummary
          error={apiError()}
          message={t('recurring.tags.mutationError')}
          fieldLabels={{ name: t('recurring.tags.inputLabel') }}
        />
      </Show>

      <Show keyed when={pendingChange()}>
        {(change) => (
          <div class="recurrence-confirmation" role="alert">
            <div>
              <strong>
                {t(
                  change.action === 'add'
                    ? 'recurring.tags.confirmAddTitle'
                    : change.action === 'remove'
                      ? 'recurring.tags.confirmRemoveTitle'
                      : 'recurring.tags.confirmCreateTitle',
                  {
                    name:
                      change.action === 'create'
                        ? change.name
                        : change.tag.name,
                  },
                )}
              </strong>
              <p>
                {t(
                  change.action === 'add'
                    ? 'recurring.tags.confirmAddMessage'
                    : change.action === 'remove'
                      ? 'recurring.tags.confirmRemoveMessage'
                      : 'recurring.tags.confirmCreateMessage',
                )}
              </p>
            </div>
            <div>
              <button
                type="button"
                disabled={isPending()}
                onClick={() => setPendingChange()}
              >
                {t('recurring.tags.cancel')}
              </button>
              <button
                type="button"
                class="recurrence-confirm-primary"
                disabled={isPending()}
                aria-busy={isPending()}
                onClick={() => void confirmChange()}
              >
                <Show when={isPending()}>
                  <LoaderCircle class="spin" size={14} strokeWidth={2} />
                </Show>
                {t(
                  change.action === 'add'
                    ? 'recurring.tags.confirmAdd'
                    : change.action === 'remove'
                      ? 'recurring.tags.confirmRemove'
                      : 'recurring.tags.confirmCreate',
                )}
              </button>
            </div>
          </div>
        )}
      </Show>
    </div>
  )
}

function normalizeTagName(name: string): string {
  return name.trim().replace(/\s+/g, ' ').toLocaleLowerCase()
}
