import type { navigation as enNavigation } from '@/shared/i18n/locales/en/navigation'
import type { DictionaryShape } from '@/shared/i18n/locales/types'

export const navigation = {
  primaryLabel: 'Основная навигация',
  homeLabel: 'Главная страница Менеджера задач',
  skipToContent: 'Перейти к основному содержимому',
  collapse: 'Свернуть навигацию',
  expand: 'Развернуть навигацию',
  tasks: 'Задачи',
  calendar: 'Календарь',
  recurring: 'Повторяющиеся задачи',
  chat: 'Чат',
  settings: 'Настройки',
} as const satisfies DictionaryShape<typeof enNavigation>
