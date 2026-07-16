import { createSignal, Show, untrack } from 'solid-js'

import './task-description-editor.css'

import { useI18n } from '@/shared/i18n/I18nProvider'
import { handleHorizontalTabListKeyDown } from '@/shared/ui/keyboard'
import { MarkdownContent } from '@/shared/ui/MarkdownContent'

type EditorMode = 'preview' | 'write'

export function TaskDescriptionEditor(props: {
  disabled: boolean
  error?: string
  onChange: (value: string) => void
  value: string
}) {
  const { t } = useI18n()
  const [mode, setMode] = createSignal<EditorMode>(
    untrack(() => props.value.trim().length > 0 ? 'preview' : 'write'),
  )

  return (
    <div class="task-description-field">
      <div class="task-description-header">
        <span>{t('tasks.details.fields.description')}</span>
        <div
          class="task-description-modes"
          role="tablist"
          aria-label={t('tasks.details.markdown.mode')}
          onKeyDown={(event) =>
            handleHorizontalTabListKeyDown(event, event.currentTarget)
          }
        >
          <button
            type="button"
            role="tab"
            id="task-description-write-tab"
            aria-controls="task-description-write-panel"
            aria-selected={mode() === 'write'}
            tabIndex={mode() === 'write' ? 0 : -1}
            disabled={props.disabled}
            onClick={() => setMode('write')}
          >
            {t('tasks.details.markdown.write')}
          </button>
          <button
            type="button"
            role="tab"
            id="task-description-preview-tab"
            aria-controls="task-description-preview-panel"
            aria-selected={mode() === 'preview'}
            tabIndex={mode() === 'preview' ? 0 : -1}
            disabled={props.disabled}
            onClick={() => setMode('preview')}
          >
            {t('tasks.details.markdown.preview')}
          </button>
        </div>
      </div>

      <Show
        when={mode() === 'write'}
        fallback={
          <div
            id="task-description-preview-panel"
            class="task-description-preview"
            role="tabpanel"
            aria-labelledby="task-description-preview-tab"
          >
            <Show
              when={props.value.trim().length > 0}
              fallback={
                <span class="task-details-empty-value">
                  {t('tasks.details.fields.descriptionPlaceholder')}
                </span>
              }
            >
              <MarkdownContent source={props.value} />
            </Show>
          </div>
        }
      >
        <div
          id="task-description-write-panel"
          role="tabpanel"
          aria-labelledby="task-description-write-tab"
        >
          <textarea
            name="description"
            value={props.value}
            placeholder={t('tasks.details.fields.descriptionPlaceholder')}
            rows={7}
            disabled={props.disabled}
            aria-invalid={props.error === undefined ? undefined : 'true'}
            aria-describedby={[
              'task-description-markdown-hint',
              props.error === undefined ? undefined : 'task-description-error',
            ].filter(Boolean).join(' ')}
            onInput={(event) => props.onChange(event.currentTarget.value)}
          />
          <small id="task-description-markdown-hint">
            {t('tasks.details.markdown.hint')}
          </small>
          <Show when={props.error}>
            {(error) => (
              <small id="task-description-error" class="task-description-error">
                {error()}
              </small>
            )}
          </Show>
        </div>
      </Show>
    </div>
  )
}
