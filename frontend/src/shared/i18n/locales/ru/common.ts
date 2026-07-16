import type { common as enCommon } from '@/shared/i18n/locales/en/common'
import type { DictionaryShape } from '@/shared/i18n/locales/types'

export const common = {
  appName: 'Менеджер задач',
  actions: {
    cancel: 'Отмена',
    retry: 'Повторить',
    refreshTasks: 'Обновить задачи',
    returnToTasks: 'Вернуться к задачам',
  },
  errors: {
    supportDetails: 'Технические сведения',
    requestId: 'Идентификатор запроса: {{requestId}}',
  },
  network: {
    offlineTitle: 'Нет подключения к сети',
    offlineMessage: 'Подключитесь к сети, чтобы восстановить сессию и продолжить работу.',
    offlineNotice: 'Нет подключения. Изменения нельзя сохранить до восстановления связи.',
  },
  language: {
    title: 'Язык',
    description: 'Выберите язык интерфейса приложения.',
    english: 'Английский',
    russian: 'Русский',
  },
  theme: {
    title: 'Оформление',
    description: 'Выберите светлую, тёмную или системную тему.',
    light: 'Светлая',
    dark: 'Тёмная',
    system: 'Системная',
  },
  validation: {
    summary: 'Проверьте выделенные поля и повторите попытку.',
    required: 'Заполните это поле.',
    invalidEmail: 'Введите корректный адрес электронной почты.',
    invalidValue: 'Введите корректное значение.',
    invalidDateTime: 'Введите дату и время полностью.',
    tooShort: 'Введите не менее {{count}} символов.',
    tooLong: 'Введите не более {{count}} символов.',
  },
  dateTime: {
    done: 'Готово',
    hours: 'Часы',
    minutes: 'Минуты',
    month: 'Месяц',
  },
  unsavedChanges: {
    title: 'Отменить несохраненные изменения?',
    message: 'Изменения на этом экране еще не сохранены.',
    stay: 'Продолжить редактирование',
    discard: 'Отменить изменения',
  },
  pages: {
    calendar: {
      title: 'Календарь',
      description:
        'Просматривайте дедлайны и запланированные задачи по месяцам, неделям или на временной шкале.',
      emptyTitle: 'Календарь пока не подключен',
      emptyMessage:
        'Здесь появятся запланированные задачи и экземпляры повторяющихся задач.',
    },
    recurring: {
      title: 'Повторяющиеся задачи',
      description:
        'Просматривайте шаблоны повторяющихся задач, правила и будущие экземпляры.',
      emptyTitle: 'Повторяющиеся задачи пока не подключены',
      emptyMessage:
        'Здесь появятся настройки повторяющихся задач и их следующие экземпляры.',
    },
    chat: {
      title: 'Чат',
      description: 'История диалогов, планы выполнения и ответы ассистента.',
      emptyTitle: 'Чат пока не подключен',
      emptyMessage:
        'Здесь появятся история диалога и процесс выполнения запроса.',
    },
    settings: {
      title: 'Настройки',
      description: 'Данные учетной записи и настройки приложения.',
    },
    notFound: {
      title: 'Страница не найдена',
      description: 'Запрошенной страницы не существует.',
    },
  },
} as const satisfies DictionaryShape<typeof enCommon>
