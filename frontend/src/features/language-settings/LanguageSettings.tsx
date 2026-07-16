import Languages from 'lucide-solid/icons/languages'
import { For } from 'solid-js'

import { supportedLocales } from '@/shared/i18n/config'
import { useI18n } from '@/shared/i18n/I18nProvider'
import type { Locale, TranslationKey } from '@/shared/i18n/types'

const localeLabelKeys: Record<Locale, TranslationKey> = {
  en: 'common.language.english',
  ru: 'common.language.russian',
}

export function LanguageSettings() {
  const { locale, setLocale, t } = useI18n()

  return (
    <section class="settings-section" aria-labelledby="language-settings-title">
      <header class="settings-section-header">
        <span class="settings-section-icon" aria-hidden="true">
          <Languages size={19} strokeWidth={1.9} />
        </span>
        <div>
          <h2 id="language-settings-title">{t('common.language.title')}</h2>
          <p>{t('common.language.description')}</p>
        </div>
      </header>

      <div class="preference-options">
        <For each={supportedLocales}>
          {(option) => (
            <button
              type="button"
              class="preference-option"
              classList={{ 'preference-option--active': locale() === option.code }}
              aria-pressed={locale() === option.code}
              aria-label={t(localeLabelKeys[option.code])}
              onClick={() => void setLocale(option.code)}
            >
              <span class="language-code">{option.code.toUpperCase()}</span>
              <span>{t(localeLabelKeys[option.code])}</span>
            </button>
          )}
        </For>
      </div>
    </section>
  )
}
