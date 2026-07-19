import type { auth as enAuth } from '@/shared/i18n/locales/en/auth'
import type { DictionaryShape } from '@/shared/i18n/locales/types'

export const auth = {
  login: {
    title: 'Вход',
    description: 'Продолжите работу с задачами и ассистентом.',
    submit: 'Войти',
    submitting: 'Выполняется вход',
    noAccount: 'Впервые в Менеджере задач?',
    registerLink: 'Создать аккаунт',
  },
  register: {
    title: 'Создание аккаунта',
    description: 'Подготовьте свое рабочее пространство.',
    submit: 'Создать аккаунт',
    submitting: 'Создается аккаунт',
    hasAccount: 'Уже есть аккаунт?',
    loginLink: 'Войти',
  },
  fields: {
    email: 'Электронная почта',
    password: 'Пароль',
    firstName: 'Имя',
    lastName: 'Фамилия',
    middleName: 'Отчество',
    optional: 'необязательно',
    showPassword: 'Показать пароль',
    hidePassword: 'Скрыть пароль',
    passwordHint: 'Не менее 8 символов, без пробелов в начале и конце.',
  },
  errors: {
    invalidCredentials: 'Неверная электронная почта или пароль.',
    emailExists: 'Аккаунт с такой электронной почтой уже существует.',
    validation: 'Проверьте введенные данные и повторите попытку.',
    unavailable: 'Сервер недоступен. Проверьте соединение и повторите попытку.',
    generic: 'Не удалось выполнить запрос. Повторите попытку.',
  },
  validation: {
    passwordWhitespace: 'Пароль не может начинаться или заканчиваться пробелом.',
  },
  session: {
    loading: 'Восстановление сессии',
    unavailableTitle: 'Не удалось восстановить сессию',
    unavailableMessage: 'Проверьте соединение и повторите попытку.',
  },
  account: {
    title: 'Аккаунт',
    description: 'Изменение данных профиля и управление текущей сессией.',
    emailVerified: 'Подтверждена',
    emailUnverified: 'Не подтверждена',
    verificationBenefits:
      'Подтверждение почты требуется для создания повторяющихся задач и увеличивает лимит запросов к ассистенту.',
    signedInAs: 'Выполнен вход: {{email}}',
    save: 'Сохранить изменения',
    saving: 'Сохранение изменений',
    saved: 'Изменения профиля сохранены.',
    signOut: 'Выйти',
  },
} as const satisfies DictionaryShape<typeof enAuth>
