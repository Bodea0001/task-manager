import { assistant } from '@/shared/i18n/locales/ru/assistant'
import { auth } from '@/shared/i18n/locales/ru/auth'
import { calendar } from '@/shared/i18n/locales/ru/calendar'
import { chat } from '@/shared/i18n/locales/ru/chat'
import { common } from '@/shared/i18n/locales/ru/common'
import { navigation } from '@/shared/i18n/locales/ru/navigation'
import { recurring } from '@/shared/i18n/locales/ru/recurring'
import { tasks } from '@/shared/i18n/locales/ru/tasks'
import type { enTranslation } from '@/shared/i18n/locales/en'
import type { DictionaryShape } from '@/shared/i18n/locales/types'

export const ruTranslation = {
  assistant,
  auth,
  calendar,
  chat,
  common,
  navigation,
  recurring,
  tasks,
} as const satisfies DictionaryShape<typeof enTranslation>
