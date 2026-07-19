import { Route, Router } from '@solidjs/router'
import { QueryClient, QueryClientProvider } from '@tanstack/solid-query'
import LoaderCircle from 'lucide-solid/icons/loader-circle'
import { lazy, Suspense } from 'solid-js'

import { ApplicationRoot } from '@/app/ApplicationRoot'
import { AuthProvider, useAuth } from '@/features/auth/AuthProvider'
import { CalendarPage } from '@/pages/calendar/CalendarPage'
import { ChatPage } from '@/pages/chat/ChatPage'
import { LoginPage } from '@/pages/login/LoginPage'
import { NotFoundPage } from '@/pages/not-found/NotFoundPage'
import { RegisterPage } from '@/pages/register/RegisterPage'
import { SettingsPage } from '@/pages/settings/SettingsPage'
import { TasksPage } from '@/pages/tasks/TasksPage'
import { I18nProvider, useI18n } from '@/shared/i18n/I18nProvider'
import { OnlineStatusProvider } from '@/shared/network/OnlineStatusProvider'
import { ThemeProvider } from '@/shared/theme/ThemeProvider'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30_000,
    },
  },
})

const LazyRecurringPage = lazy(async () => ({
  default: (await import('@/pages/recurring/RecurringPage')).RecurringPage,
}))

function RecurringRoute() {
  const auth = useAuth()
  const { t } = useI18n()
  return (
    <Suspense
      fallback={
        <section
          class="route-loading-state"
          role="status"
          aria-label={t('recurring.states.loading')}
        >
          <LoaderCircle class="spin" size={24} strokeWidth={1.8} />
          <span>{t('recurring.states.loading')}</span>
        </section>
      }
    >
      <LazyRecurringPage emailVerified={auth.user()?.email_verified === true} />
    </Suspense>
  )
}

export function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <OnlineStatusProvider>
            <AuthProvider>
              <Router root={ApplicationRoot}>
                <Route path="/login" component={LoginPage} />
                <Route path="/register" component={RegisterPage} />
                <Route path="/" component={TasksPage} />
                <Route path="/calendar" component={CalendarPage} />
                <Route path="/recurring" component={RecurringRoute} />
                <Route path="/chat" component={ChatPage} />
                <Route path="/settings" component={SettingsPage} />
                <Route path="*404" component={NotFoundPage} />
              </Router>
            </AuthProvider>
          </OnlineStatusProvider>
        </QueryClientProvider>
      </I18nProvider>
    </ThemeProvider>
  )
}
