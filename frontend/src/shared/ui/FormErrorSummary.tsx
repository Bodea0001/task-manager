import { For, Show } from 'solid-js'

import './form-error-summary.css'

import type { FormApiError } from '@/shared/forms/apiErrors'
import { useI18n } from '@/shared/i18n/I18nProvider'

export function FormErrorSummary(props: {
  error?: FormApiError
  fieldLabels?: Readonly<Record<string, string>>
  message: string
}) {
  const { t } = useI18n()
  const fieldEntries = () => Object.entries(props.error?.fieldErrors || {})
  const showDetails = () =>
    fieldEntries().length > 1 || (props.error?.generalErrors.length || 0) > 0

  return (
    <div class="form-error-summary" role="alert">
      <p>{props.message}</p>
      <Show when={showDetails()}>
        <ul>
          <For each={fieldEntries()}>
            {([field, message]) => (
              <li>
                <Show when={props.fieldLabels?.[field]}>
                  {(label) => <strong>{label()}: </strong>}
                </Show>
                {message}
              </li>
            )}
          </For>
          <For each={props.error?.generalErrors || []}>
            {(message) => <li>{message}</li>}
          </For>
        </ul>
      </Show>
      <Show when={props.error?.requestId}>
        {(requestId) => (
          <details>
            <summary>{t('common.errors.supportDetails')}</summary>
            <code>{t('common.errors.requestId', { requestId: requestId() })}</code>
          </details>
        )}
      </Show>
    </div>
  )
}
