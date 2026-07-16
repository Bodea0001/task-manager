import type { assistant as enAssistant } from '@/shared/i18n/locales/en/assistant'
import type { DictionaryShape } from '@/shared/i18n/locales/types'

export const assistant = {
  label: 'Ассистент',
  title: 'Ассистент',
  subtitle: 'Менеджер задач',
  collapsedLabel: 'Свёрнутая панель ассистента',
  collapsePanel: 'Свернуть панель ассистента',
  expandPanel: 'Развернуть панель ассистента',
  openMobile: 'Открыть ассистента',
  closeMobile: 'Закрыть ассистента',
  openWorkspace: 'Открыть чат',
  emptyTitle: 'Начните диалог',
  emptyMessage:
    'Попросите ассистента найти, упорядочить или изменить ваши задачи.',
} as const satisfies DictionaryShape<typeof enAssistant>
