import Monitor from 'lucide-solid/icons/monitor'
import Moon from 'lucide-solid/icons/moon'
import Palette from 'lucide-solid/icons/palette'
import Sun from 'lucide-solid/icons/sun'
import type { LucideIcon } from 'lucide-solid'
import { For } from 'solid-js'

import { useI18n } from '@/shared/i18n/I18nProvider'
import type { TranslationKey } from '@/shared/i18n/types'
import { useTheme, type ThemeMode } from '@/shared/theme/ThemeProvider'

interface ThemeOption {
  icon: LucideIcon
  labelKey: TranslationKey
  mode: ThemeMode
}

const themeOptions: readonly ThemeOption[] = [
  { mode: 'light', labelKey: 'common.theme.light', icon: Sun },
  { mode: 'dark', labelKey: 'common.theme.dark', icon: Moon },
  { mode: 'system', labelKey: 'common.theme.system', icon: Monitor },
]

export function ThemeSettings() {
  const { t } = useI18n()
  const theme = useTheme()

  return (
    <section class="settings-section" aria-labelledby="theme-settings-title">
      <header class="settings-section-header">
        <span class="settings-section-icon" aria-hidden="true">
          <Palette size={19} strokeWidth={1.9} />
        </span>
        <div>
          <h2 id="theme-settings-title">{t('common.theme.title')}</h2>
          <p>{t('common.theme.description')}</p>
        </div>
      </header>

      <div class="preference-options preference-options--three">
        <For each={themeOptions}>
          {(option) => (
            <button
              type="button"
              class="preference-option"
              classList={{ 'preference-option--active': theme.mode() === option.mode }}
              aria-pressed={theme.mode() === option.mode}
              onClick={() => theme.setMode(option.mode)}
            >
              <option.icon aria-hidden="true" size={17} strokeWidth={1.9} />
              <span>{t(option.labelKey)}</span>
            </button>
          )}
        </For>
      </div>
    </section>
  )
}
