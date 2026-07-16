import { AccountSettings } from '@/features/auth/AccountSettings'
import { LanguageSettings } from '@/features/language-settings/LanguageSettings'
import { ThemeSettings } from '@/features/theme-settings/ThemeSettings'
import { useI18n } from '@/shared/i18n/I18nProvider'
import { Page } from '@/shared/ui/Page'

export function SettingsPage() {
  const { t } = useI18n()
  return (
    <Page
      title={t('common.pages.settings.title')}
      description={t('common.pages.settings.description')}
    >
      <AccountSettings />
      <ThemeSettings />
      <LanguageSettings />
    </Page>
  )
}
