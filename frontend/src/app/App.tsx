import { Route, Router } from '@solidjs/router'
import { QueryClient, QueryClientProvider } from '@tanstack/solid-query'
import { lazy } from 'solid-js'

import { ApplicationRoot } from '@/app/ApplicationRoot'
import { AuthProvider } from '@/features/auth/AuthProvider'
import { CalendarPage } from '@/pages/calendar/CalendarPage'
import { ChatPage } from '@/pages/chat/ChatPage'
import { LoginPage } from '@/pages/login/LoginPage'
import { NotFoundPage } from '@/pages/not-found/NotFoundPage'
import { RegisterPage } from '@/pages/register/RegisterPage'
import { SettingsPage } from '@/pages/settings/SettingsPage'
import { TasksPage } from '@/pages/tasks/TasksPage'
import { I18nProvider } from '@/shared/i18n/I18nProvider'
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

const RecurringPage = lazy(async () => ({
  default: (await import('@/pages/recurring/RecurringPage')).RecurringPage,
}))

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
                <Route path="/recurring" component={RecurringPage} />
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
