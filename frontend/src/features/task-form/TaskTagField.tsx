import { createMutation, createQuery, useQueryClient } from '@tanstack/solid-query'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import Plus from 'lucide-solid/icons/plus'
import Trash2 from 'lucide-solid/icons/trash-2'
import X from 'lucide-solid/icons/x'
import {
  createEffect,
  createMemo,
  createSignal,
  For,
  Match,
  Show,
  Switch,
} from 'solid-js'

import './task-tag-field.css'

import { createTag, deleteTag, listTags, TAGS_QUERY_KEY } from '@/entities/tag/api'
import { addTagToCache, removeTagFromCache } from '@/entities/tag/cache'
import type { Tag } from '@/entities/tag/model'
import { removeTagFromTaskCaches } from '@/entities/task/cache'
import {
  clearFormApiField,
  type FormApiError,
  toFormApiError,
} from '@/shared/forms/apiErrors'
import { useI18n } from '@/shared/i18n/I18nProvider'
import { FormErrorSummary } from '@/shared/ui/FormErrorSummary'

export function TaskTagField(props: {
  disabled?: boolean
  id: string
  knownTags?: readonly Tag[]
  onChange: (tagIds: readonly string[]) => void
  onPendingChange?: (isPending: boolean) => void
  selectedTagIds: readonly string[]
}) {
  const queryClient = useQueryClient()
  const { t } = useI18n()
  const [tagName, setTagName] = createSignal('')
  const [hasCreationError, setCreationError] = createSignal(false)
  const [creationApiError, setCreationApiError] = createSignal<FormApiError>()
  const [tagToDelete, setTagToDelete] = createSignal<Tag>()
  const [hasDeletionError, setDeletionError] = createSignal(false)
  const [deletionApiError, setDeletionApiError] = createSignal<FormApiError>()
  const tagsQuery = createQuery(() => ({
    queryKey: TAGS_QUERY_KEY,
    queryFn: listTags,
    staleTime: 30_000,
  }))
  const creation = createMutation(() => ({
    mutationFn: createTag,
    onSuccess: (tag) => {
      addTagToCache(queryClient, tag)
      selectTag(tag.tag_id)
      setTagName('')
    },
  }))
  const deletion = createMutation(() => ({
    mutationFn: deleteTag,
    onSuccess: (_, tagId) => {
      removeTagFromCache(queryClient, tagId)
      props.onChange(
        props.selectedTagIds.filter((selectedId) => selectedId !== tagId),
      )
      setTagToDelete()
      removeTagFromTaskCaches(queryClient, tagId)
    },
  }))
  const tags = createMemo(() => {
    const byId = new Map<string, Tag>()
    for (const tag of props.knownTags || []) {
      byId.set(tag.tag_id, tag)
    }
    for (const tag of tagsQuery.data?.tags || []) {
      byId.set(tag.tag_id, tag)
    }
    return [...byId.values()]
  })
  const normalizedTagName = () => normalizeTagName(tagName())
  const matchingTag = () =>
    tags().find((tag) => normalizeTagName(tag.name) === normalizedTagName())
  const visibleTags = createMemo(() => {
    const query = normalizedTagName()
    if (query.length === 0) {
      return tags()
    }
    return tags().filter((tag) => normalizeTagName(tag.name).includes(query))
  })
  const cannotSubmitTag = () => {
    const match = matchingTag()
    return (
      props.disabled ||
      creation.isPending ||
      deletion.isPending ||
      normalizedTagName().length === 0 ||
      (match !== undefined && props.selectedTagIds.includes(match.tag_id))
    )
  }

  createEffect(() =>
    props.onPendingChange?.(creation.isPending || deletion.isPending),
  )

  function selectTag(tagId: string) {
    if (!props.selectedTagIds.includes(tagId)) {
      props.onChange([...props.selectedTagIds, tagId])
    }
  }

  function toggleTag(tagId: string) {
    if (props.selectedTagIds.includes(tagId)) {
      props.onChange(props.selectedTagIds.filter((selectedId) => selectedId !== tagId))
      return
    }
    selectTag(tagId)
  }

  async function createOrSelectTag() {
    if (cannotSubmitTag()) {
      return
    }
    setCreationError(false)
    setCreationApiError()
    const match = matchingTag()
    if (match !== undefined) {
      selectTag(match.tag_id)
      setTagName('')
      return
    }
    try {
      await creation.mutateAsync(tagName().trim())
    } catch (error) {
      setCreationApiError(toFormApiError(error, { fields: ['name'] }))
      setCreationError(true)
    }
  }

  async function confirmTagDeletion() {
    const tag = tagToDelete()
    if (tag === undefined || deletion.isPending) {
      return
    }
    setDeletionError(false)
    setDeletionApiError()
    try {
      await deletion.mutateAsync(tag.tag_id)
    } catch (error) {
      setDeletionApiError(toFormApiError(error, { fields: [] }))
      setDeletionError(true)
    }
  }

  return (
    <section class="task-form-section task-tag-field" aria-labelledby={`${props.id}-title`}>
      <div class="task-tag-field-heading">
        <div>
          <h3 id={`${props.id}-title`}>{t('tasks.details.fields.tags')}</h3>
          <p>{t('tasks.tags.hint')}</p>
        </div>
        <Show when={props.selectedTagIds.length > 0}>
          <span>{t('tasks.tags.selected', { count: props.selectedTagIds.length })}</span>
        </Show>
      </div>

      <Switch>
        <Match when={tagsQuery.isPending && tags().length === 0}>
          <div class="task-tag-field-state">
            <LoaderCircle class="spin" size={15} strokeWidth={2} />
            {t('tasks.tags.loading')}
          </div>
        </Match>
        <Match when={tags().length === 0 && normalizedTagName().length === 0}>
          <p class="task-tag-field-empty">{t('tasks.tags.empty')}</p>
        </Match>
        <Match when={visibleTags().length > 0}>
          <div class="task-tag-options" role="group" aria-label={t('tasks.tags.optionsLabel')}>
            <For each={visibleTags()}>
              {(tag) => (
                <div class="task-tag-option-group">
                  <button
                    type="button"
                    class="task-tag-option"
                    classList={{
                      'task-tag-option--selected': props.selectedTagIds.includes(tag.tag_id),
                    }}
                    aria-pressed={props.selectedTagIds.includes(tag.tag_id)}
                    title={t(
                      props.selectedTagIds.includes(tag.tag_id)
                        ? 'tasks.tags.removeFromTask'
                        : 'tasks.tags.addToTask',
                      { name: tag.name },
                    )}
                    disabled={props.disabled || creation.isPending || deletion.isPending}
                    onClick={() => toggleTag(tag.tag_id)}
                  >
                    <Show when={props.selectedTagIds.includes(tag.tag_id)}>
                      <X size={13} strokeWidth={2.4} aria-hidden="true" />
                    </Show>
                    {tag.name}
                  </button>
                  <button
                    type="button"
                    class="task-tag-delete"
                    aria-label={t('tasks.tags.delete', { name: tag.name })}
                    title={t('tasks.tags.delete', { name: tag.name })}
                    disabled={props.disabled || creation.isPending || deletion.isPending}
                    onClick={() => {
                      setDeletionError(false)
                      setDeletionApiError()
                      setTagToDelete(tag)
                    }}
                  >
                    <Trash2 size={13} strokeWidth={1.9} aria-hidden="true" />
                  </button>
                </div>
              )}
            </For>
          </div>
        </Match>
        <Match when={normalizedTagName().length > 0}>
          <p class="task-tag-field-empty">{t('tasks.tags.noMatches')}</p>
        </Match>
      </Switch>

      <div class="task-tag-create-row">
        <label class="visually-hidden" for={`${props.id}-input`}>
          {t('tasks.tags.inputLabel')}
        </label>
        <input
          id={`${props.id}-input`}
          value={tagName()}
          maxlength={100}
          disabled={props.disabled || creation.isPending}
          placeholder={t('tasks.tags.placeholder')}
          aria-invalid={creationApiError()?.fieldErrors.name !== undefined}
          aria-describedby={
            creationApiError()?.fieldErrors.name === undefined
              ? undefined
              : `${props.id}-input-error`
          }
          onInput={(event) => {
            setTagName(event.currentTarget.value)
            setCreationError(false)
            setCreationApiError((current) => clearFormApiField(current, 'name'))
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              void createOrSelectTag()
            }
          }}
        />
        <button
          type="button"
          disabled={cannotSubmitTag()}
          aria-busy={creation.isPending}
          onClick={() => void createOrSelectTag()}
        >
          <Show when={creation.isPending} fallback={<Plus size={15} strokeWidth={2.1} />}>
            <LoaderCircle class="spin" size={15} strokeWidth={2} />
          </Show>
          {t(matchingTag() === undefined ? 'tasks.tags.create' : 'tasks.tags.select')}
        </button>
      </div>

      <Show when={creationApiError()?.fieldErrors.name}>
        {(error) => (
          <small id={`${props.id}-input-error`} class="task-tag-field-error">
            {error()}
          </small>
        )}
      </Show>

      <Show when={tagsQuery.isError}>
        <p class="task-tag-field-error" role="alert">{t('tasks.tags.loadError')}</p>
      </Show>
      <Show when={hasCreationError()}>
        <FormErrorSummary
          error={creationApiError()}
          message={t('tasks.tags.createError')}
          fieldLabels={{ name: t('tasks.tags.inputLabel') }}
        />
      </Show>
      <Show when={hasDeletionError()}>
        <FormErrorSummary
          error={deletionApiError()}
          message={t('tasks.tags.deleteError')}
        />
      </Show>

      <Show when={tagToDelete()}>
        {(tag) => (
          <div class="task-tag-delete-confirmation" role="alert">
            <div>
              <strong>{t('tasks.tags.deleteTitle', { name: tag().name })}</strong>
              <p>{t('tasks.tags.deleteMessage')}</p>
            </div>
            <div class="task-tag-delete-actions">
              <button
                type="button"
                disabled={deletion.isPending}
                onClick={() => setTagToDelete()}
              >
                {t('common.actions.cancel')}
              </button>
              <button
                type="button"
                class="task-tag-delete-confirm"
                disabled={deletion.isPending}
                aria-busy={deletion.isPending}
                onClick={() => void confirmTagDeletion()}
              >
                <Show when={deletion.isPending}>
                  <LoaderCircle class="spin" size={14} strokeWidth={2} />
                </Show>
                {t('tasks.tags.confirmDelete')}
              </button>
            </div>
          </div>
        )}
      </Show>
    </section>
  )
}

function normalizeTagName(name: string): string {
  return name.trim().replace(/\s+/g, ' ').toLocaleLowerCase()
}
