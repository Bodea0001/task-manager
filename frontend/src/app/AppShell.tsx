import { A, useLocation } from '@solidjs/router'
import CalendarDays from 'lucide-solid/icons/calendar-days'
import ListTodo from 'lucide-solid/icons/list-todo'
import MessageSquareText from 'lucide-solid/icons/message-square-text'
import PanelLeftClose from 'lucide-solid/icons/panel-left-close'
import PanelLeftOpen from 'lucide-solid/icons/panel-left-open'
import PanelRightOpen from 'lucide-solid/icons/panel-right-open'
import Repeat2 from 'lucide-solid/icons/repeat-2'
import Settings from 'lucide-solid/icons/settings'
import Sparkles from 'lucide-solid/icons/sparkles'
import {
  createEffect,
  createSignal,
  For,
  on,
  onCleanup,
  Show,
  type JSX,
  type ParentProps,
} from 'solid-js'

import { AssistantPanel } from '@/features/assistant-panel/AssistantPanel'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import { BrandMark } from '@/shared/ui/BrandMark'

interface NavigationItem {
  href: string
  icon: (props: { size: number; strokeWidth: number }) => JSX.Element
  labelKey: TranslationKey
  end?: boolean
}

const navigationItems: readonly NavigationItem[] = [
  { href: '/', icon: ListTodo, labelKey: 'navigation.tasks', end: true },
  {
    href: '/calendar',
    icon: CalendarDays,
    labelKey: 'navigation.calendar',
  },
  { href: '/recurring', icon: Repeat2, labelKey: 'navigation.recurring' },
  { href: '/chat', icon: MessageSquareText, labelKey: 'navigation.chat' },
  { href: '/settings', icon: Settings, labelKey: 'navigation.settings' },
]

const NAVIGATION_STORAGE_KEY = 'task-manager.navigation-collapsed'
const ASSISTANT_STORAGE_KEY = 'task-manager.assistant-collapsed'

export function AppShell(props: ParentProps) {
  const { t } = useI18n()
  const location = useLocation()
  const [isNavigationCollapsed, setNavigationCollapsed] = createSignal(
    localStorage.getItem(NAVIGATION_STORAGE_KEY) === 'true',
  )
  const [isAssistantCollapsed, setAssistantCollapsed] = createSignal(
    localStorage.getItem(ASSISTANT_STORAGE_KEY) === 'true',
  )
  const [isMobileAssistantOpen, setMobileAssistantOpen] = createSignal(false)
  let mobileAssistantToggle: HTMLButtonElement | undefined
  let mobileAssistantClose: HTMLButtonElement | undefined
  let mainContent!: HTMLElement
  const hasAssistantPanel = () => location.pathname !== '/chat'
  const navigationToggleLabel = () =>
    t(
      isNavigationCollapsed()
        ? 'navigation.expand'
        : 'navigation.collapse',
    )

  const toggleNavigation = () => {
    const nextValue = !isNavigationCollapsed()
    setNavigationCollapsed(nextValue)
    localStorage.setItem(NAVIGATION_STORAGE_KEY, String(nextValue))
  }

  const setAssistantVisibility = (collapsed: boolean) => {
    setAssistantCollapsed(collapsed)
    localStorage.setItem(ASSISTANT_STORAGE_KEY, String(collapsed))
  }

  const openMobileAssistant = () => {
    setMobileAssistantOpen(true)
    queueMicrotask(() => mobileAssistantClose?.focus())
  }

  const closeMobileAssistant = (restoreFocus = true) => {
    setMobileAssistantOpen(false)
    if (restoreFocus) queueMicrotask(() => mobileAssistantToggle?.focus())
  }

  createEffect(
    on(
      () => location.pathname,
      () => {
        closeMobileAssistant(false)
        queueMicrotask(() => mainContent.focus())
      },
      { defer: true },
    ),
  )

  createEffect(() => {
    if (!isMobileAssistantOpen()) return
    document.body.classList.add('mobile-assistant-open')
    onCleanup(() => document.body.classList.remove('mobile-assistant-open'))
  })

  return (
    <div
      class="app-shell"
      classList={{
        'app-shell--navigation-collapsed': isNavigationCollapsed(),
        'app-shell--without-assistant': !hasAssistantPanel(),
        'app-shell--assistant-collapsed':
          hasAssistantPanel() && isAssistantCollapsed(),
      }}
    >
      <a
        class="skip-link"
        href="#main-content"
        onClick={() => queueMicrotask(() => mainContent.focus())}
      >
        {t('navigation.skipToContent')}
      </a>
      <header class="mobile-header">
        <Brand collapsed={false} />
        <Show when={hasAssistantPanel()}>
          <button
            ref={(element) => {
              mobileAssistantToggle = element
            }}
            type="button"
            class="icon-button mobile-assistant-toggle"
            aria-label={t('assistant.openMobile')}
            title={t('assistant.openMobile')}
            aria-controls="assistant-panel"
            aria-expanded={isMobileAssistantOpen()}
            onClick={openMobileAssistant}
          >
            <Sparkles size={18} strokeWidth={1.9} />
          </button>
        </Show>
      </header>

      <aside class="sidebar">
        <div class="sidebar-header">
          <Brand collapsed={isNavigationCollapsed()} />
          <button
            type="button"
            class="icon-button sidebar-toggle"
            aria-label={navigationToggleLabel()}
            title={navigationToggleLabel()}
            onClick={toggleNavigation}
          >
            <Show
              when={isNavigationCollapsed()}
              fallback={<PanelLeftClose size={18} strokeWidth={1.9} />}
            >
              <PanelLeftOpen size={18} strokeWidth={1.9} />
            </Show>
          </button>
        </div>
        <Navigation
          class="desktop-navigation"
          collapsed={isNavigationCollapsed()}
          replace={location.search.includes('create=')}
        />
      </aside>

      <main ref={mainContent} class="workspace" id="main-content" tabIndex={-1}>
        {props.children}
      </main>

      <Show when={hasAssistantPanel()}>
        <button
          type="button"
          class="mobile-assistant-backdrop"
          classList={{
            'mobile-assistant-backdrop--open': isMobileAssistantOpen(),
          }}
          aria-label={t('assistant.closeMobile')}
          aria-hidden={!isMobileAssistantOpen() ? 'true' : undefined}
          tabindex={isMobileAssistantOpen() ? 0 : -1}
          onClick={() => closeMobileAssistant()}
        />
        <AssistantPanel
          mobileOpen={isMobileAssistantOpen()}
          onCollapse={() => setAssistantVisibility(true)}
          onMobileClose={() => closeMobileAssistant()}
          onMobileCloseReady={(element) => {
            mobileAssistantClose = element
          }}
        />
        <Show when={isAssistantCollapsed()}>
          <aside
            class="assistant-collapsed-rail"
            aria-label={t('assistant.collapsedLabel')}
          >
            <button
              type="button"
              class="icon-button"
              aria-label={t('assistant.expandPanel')}
              title={t('assistant.expandPanel')}
              onClick={() => setAssistantVisibility(false)}
            >
              <PanelRightOpen size={18} strokeWidth={1.9} />
            </button>
          </aside>
        </Show>
      </Show>

      <Navigation
        class="mobile-navigation"
        collapsed
        replace={location.search.includes('create=')}
      />
    </div>
  )
}

function Brand(props: { collapsed: boolean }) {
  const { t } = useI18n()
  return (
    <A class="brand" href="/" aria-label={t('navigation.homeLabel')}>
      <BrandMark />
      <Show when={!props.collapsed}>
        <span class="brand-label">{t('common.appName')}</span>
      </Show>
    </A>
  )
}

function Navigation(props: {
  class: string
  collapsed: boolean
  replace: boolean
}) {
  const { t } = useI18n()
  return (
    <nav class={props.class} aria-label={t('navigation.primaryLabel')}>
      <For each={navigationItems}>
        {(item) => (
          <A
            class="nav-link"
            activeClass="nav-link--active"
            href={item.href}
            end={item.end}
            replace={props.replace}
            aria-label={t(item.labelKey)}
            title={props.collapsed ? t(item.labelKey) : undefined}
          >
            <item.icon size={20} strokeWidth={1.9} />
            <Show when={!props.collapsed}>
              <span class="nav-label">{t(item.labelKey)}</span>
            </Show>
          </A>
        )}
      </For>
    </nav>
  )
}
