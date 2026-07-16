import { Navigate, useLocation } from '@solidjs/router'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import WifiOff from 'lucide-solid/icons/wifi-off'
import {
  createEffect,
  Match,
  on,
  Show,
  Switch,
  type ParentProps,
} from 'solid-js'

import { AppShell } from '@/app/AppShell'
import { useAuth } from '@/features/auth/AuthProvider'
import { ChatDraftProvider } from '@/features/chat/ChatDraftProvider'
import { useI18n } from '@/shared/i18n/I18nProvider'
import { useOnlineStatus } from '@/shared/network/OnlineStatusProvider'

const AUTH_PATHS = new Set(['/login', '/register'])

export function ApplicationRoot(props: ParentProps) {
  const auth = useAuth()
  const location = useLocation()
  const { t } = useI18n()
  const { isOnline } = useOnlineStatus()
  const isAuthPage = () => AUTH_PATHS.has(location.pathname)

  createEffect(
    on(
      isOnline,
      (online, previousOnline) => {
        if (online && previousOnline === false && auth.status() === 'unavailable') {
          void auth.retryInitialization()
        }
      },
      { defer: true },
    ),
  )

  return (
    <>
      <Show when={!isOnline() && auth.status() !== 'unavailable'}>
        <div class="network-status" role="status">
          <WifiOff size={17} strokeWidth={1.9} aria-hidden="true" />
          <span>{t('common.network.offlineNotice')}</span>
        </div>
      </Show>
      <Switch>
        <Match when={auth.status() === 'initializing'}>
          <main class="session-state" aria-label={t('auth.session.loading')}>
            <LoaderCircle class="spin" size={24} strokeWidth={1.8} />
            <p>{t('auth.session.loading')}</p>
          </main>
        </Match>
        <Match when={auth.status() === 'unavailable'}>
          <main class="session-state" role="alert">
            <WifiOff size={24} strokeWidth={1.8} />
            <h1>
              {t(
                isOnline()
                  ? 'auth.session.unavailableTitle'
                  : 'common.network.offlineTitle',
              )}
            </h1>
            <p>
              {t(
                isOnline()
                  ? 'auth.session.unavailableMessage'
                  : 'common.network.offlineMessage',
              )}
            </p>
            <Show when={isOnline()}>
              <button
                type="button"
                class="primary-button"
                onClick={() => void auth.retryInitialization()}
              >
                {t('common.actions.retry')}
              </button>
            </Show>
            <button
              type="button"
              class="session-sign-out"
              onClick={() => void auth.logout()}
            >
              {t('auth.account.signOut')}
            </button>
          </main>
        </Match>
        <Match when={auth.status() === 'anonymous' && !isAuthPage()}>
          <Navigate href="/login" />
        </Match>
        <Match when={auth.status() === 'authenticated' && isAuthPage()}>
          <Navigate href="/" />
        </Match>
        <Match when={isAuthPage()}>{props.children}</Match>
        <Match when={auth.status() === 'authenticated'}>
          <ChatDraftProvider userId={auth.user()!.user_id}>
            <AppShell>{props.children}</AppShell>
          </ChatDraftProvider>
        </Match>
      </Switch>
    </>
  )
}
