import { useBeforeLeave } from '@solidjs/router'
import {
  createEffect,
  createSignal,
  onCleanup,
  onMount,
  Show,
  type Accessor,
} from 'solid-js'
import { Portal } from 'solid-js/web'

import './unsaved-changes-guard.css'

import { useI18n } from '@/shared/i18n/I18nProvider'
import { trapFocus } from '@/shared/ui/keyboard'

interface UnsavedChangesController {
  allowNextNavigation: () => void
  discardChanges: () => void
  pending: Accessor<boolean>
  stay: () => void
}

/** Coordinates internal navigation and browser-level protection for a dirty form. */
export function createUnsavedChangesGuard(
  isDirty: Accessor<boolean>,
): UnsavedChangesController {
  const [pending, setPending] = createSignal(false)
  let pendingRetry: ((force?: boolean) => void) | undefined
  let allowNextNavigation = false

  useBeforeLeave((event) => {
    if (allowNextNavigation) {
      allowNextNavigation = false
      return
    }
    if (!isDirty() || event.defaultPrevented) return
    event.preventDefault()
    pendingRetry = event.retry
    setPending(true)
  })

  const handleBeforeUnload = (event: BeforeUnloadEvent) => {
    if (!isDirty()) return
    event.preventDefault()
    event.returnValue = ''
  }

  onMount(() => window.addEventListener('beforeunload', handleBeforeUnload))
  onCleanup(() => {
    window.removeEventListener('beforeunload', handleBeforeUnload)
    pendingRetry = undefined
  })

  createEffect(() => {
    if (!isDirty() && pending()) {
      pendingRetry = undefined
      setPending(false)
    }
  })

  return {
    allowNextNavigation: () => {
      allowNextNavigation = true
      queueMicrotask(() => {
        allowNextNavigation = false
      })
    },
    discardChanges: () => {
      const retry = pendingRetry
      pendingRetry = undefined
      setPending(false)
      retry?.(true)
    },
    pending,
    stay: () => {
      pendingRetry = undefined
      setPending(false)
    },
  }
}

export function UnsavedChangesDialog(props: {
  controller: UnsavedChangesController
}) {
  const { t } = useI18n()
  let stayButton!: HTMLButtonElement
  let returnFocus: HTMLElement | undefined

  createEffect(() => {
    if (props.controller.pending()) {
      const activeElement = document.activeElement
      if (activeElement instanceof HTMLElement) returnFocus = activeElement
      queueMicrotask(() => stayButton.focus())
      return
    }
    const target = returnFocus
    returnFocus = undefined
    if (target !== undefined) {
      queueMicrotask(() => {
        if (target.isConnected) target.focus()
      })
    }
  })

  return (
    <Show when={props.controller.pending()}>
      <Portal>
        <div class="unsaved-changes-backdrop">
          <section
            class="unsaved-changes-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="unsaved-changes-title"
            aria-describedby="unsaved-changes-description"
            onKeyDown={(event) => {
              if (event.key === 'Escape') props.controller.stay()
              trapFocus(event, event.currentTarget)
            }}
          >
            <div>
              <h2 id="unsaved-changes-title">
                {t('common.unsavedChanges.title')}
              </h2>
              <p id="unsaved-changes-description">
                {t('common.unsavedChanges.message')}
              </p>
            </div>
            <div class="unsaved-changes-actions">
              <button
                ref={stayButton}
                type="button"
                onClick={() => props.controller.stay()}
              >
                {t('common.unsavedChanges.stay')}
              </button>
              <button
                type="button"
                class="unsaved-changes-discard"
                onClick={() => props.controller.discardChanges()}
              >
                {t('common.unsavedChanges.discard')}
              </button>
            </div>
          </section>
        </div>
      </Portal>
    </Show>
  )
}
