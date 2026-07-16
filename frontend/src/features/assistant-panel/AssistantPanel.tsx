import { A } from '@solidjs/router'
import Expand from 'lucide-solid/icons/expand'
import PanelRightClose from 'lucide-solid/icons/panel-right-close'
import Sparkles from 'lucide-solid/icons/sparkles'
import X from 'lucide-solid/icons/x'

import { ChatWorkspace } from '@/features/chat/ChatWorkspace'
import { useI18n } from '@/shared/i18n/I18nProvider'
import { trapFocus } from '@/shared/ui/keyboard'

export function AssistantPanel(props: {
  mobileOpen: boolean
  onCollapse: () => void
  onMobileClose: () => void
  onMobileCloseReady: (element: HTMLButtonElement) => void
}) {
  const { t } = useI18n()
  return (
    <aside
      id="assistant-panel"
      class="assistant-panel"
      classList={{ 'assistant-panel--mobile-open': props.mobileOpen }}
      aria-label={t('assistant.label')}
      aria-modal={props.mobileOpen ? 'true' : undefined}
      role={props.mobileOpen ? 'dialog' : undefined}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && props.mobileOpen) props.onMobileClose()
        if (props.mobileOpen) trapFocus(event, event.currentTarget)
      }}
    >
      <header class="assistant-header">
        <div class="assistant-title">
          <span class="assistant-mark" aria-hidden="true">
            <Sparkles size={16} strokeWidth={2} />
          </span>
          <div>
            <strong>{t('assistant.title')}</strong>
            <span>{t('assistant.subtitle')}</span>
          </div>
        </div>
        <div class="assistant-header-actions">
          <button
            type="button"
            class="icon-button assistant-desktop-collapse"
            aria-label={t('assistant.collapsePanel')}
            title={t('assistant.collapsePanel')}
            onClick={() => props.onCollapse()}
          >
            <PanelRightClose size={18} strokeWidth={1.9} />
          </button>
          <button
            ref={props.onMobileCloseReady}
            type="button"
            class="icon-button assistant-mobile-close"
            aria-label={t('assistant.closeMobile')}
            title={t('assistant.closeMobile')}
            onClick={() => props.onMobileClose()}
          >
            <X size={18} strokeWidth={1.9} />
          </button>
          <A
            class="icon-button"
            href="/chat"
            aria-label={t('assistant.openWorkspace')}
            title={t('assistant.openWorkspace')}
          >
            <Expand size={17} strokeWidth={1.9} />
          </A>
        </div>
      </header>

      <ChatWorkspace mode="panel" />
    </aside>
  )
}
